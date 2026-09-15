"""Deep PyTorch Architectures for Space Weather Solar Flare Forecasting on Aditya-L1.

Includes:
1. CNNLSTMSolarForecaster: Multi-scale 1D Dilated ConvNet + Bidirectional LSTM + Multi-Horizon Heads.
2. SpatioTemporalGraphTransformer: Multi-Detector Graph Attention + Temporal Transformer + Neupert PINN Loss.
3. BinaryFocalLoss: Asymmetric class-imbalance loss for rare extreme space weather events.
4. Physics-Informed Regularization (PINN) enforcing Neupert energy conservation:
      dSXR/dt = alpha * HXR - beta * SXR
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.utils.data import Dataset, DataLoader
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    torch = None
    nn = None
    F = None
    Dataset = object
    DataLoader = None


# ==============================================================================
# 1. Losses & Utilities
# ==============================================================================

if HAS_TORCH:
    class BinaryFocalLoss(nn.Module):
        """Asymmetric Focal Loss for rare solar flare precursor detection."""
        def __init__(self, alpha: float = 0.85, gamma: float = 2.5):
            super().__init__()
            self.alpha = alpha
            self.gamma = gamma

        def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
            bce_loss = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
            probs = torch.sigmoid(logits)
            p_t = targets * probs + (1.0 - targets) * (1.0 - probs)
            alpha_factor = targets * self.alpha + (1.0 - targets) * (1.0 - self.alpha)
            modulating_factor = torch.pow((1.0 - p_t).clamp(min=1e-6), self.gamma)
            return (alpha_factor * modulating_factor * bce_loss).mean()


    class NeupertPhysicsLoss(nn.Module):
        """Physics-Informed Neupert Energy Conservation Loss.
        Enforces d(SXR)/dt = alpha * HXR - beta * SXR
        """
        def __init__(self):
            super().__init__()

        def forward(
            self,
            dsxr_dt_pred: torch.Tensor,
            sxr: torch.Tensor,
            hxr: torch.Tensor,
            alpha: torch.Tensor,
            beta: torch.Tensor,
        ) -> torch.Tensor:
            neupert_target = alpha * hxr - beta * sxr
            return F.mse_loss(dsxr_dt_pred, neupert_target)


    # ==============================================================================
    # 2. Architecture 1: Multi-Scale CNN-LSTM Forecaster
    # ==============================================================================

    class CNNLSTMSolarForecaster(nn.Module):
        """Multi-Scale 1D ConvNet + Bidirectional LSTM + Multi-Horizon Forecast Heads."""
        def __init__(
            self,
            in_channels: int = 8,
            conv_channels: int = 64,
            lstm_hidden: int = 64,
            num_lstm_layers: int = 2,
            dropout: float = 0.15,
        ):
            super().__init__()
            self.in_channels = in_channels
            self.conv_channels = conv_channels

            # Multi-scale 1D Convolutions (kernel 3, 5, 7)
            c3_ch = conv_channels // 2
            c5_ch = conv_channels // 4
            c7_ch = conv_channels - c3_ch - c5_ch
            self.conv3 = nn.Conv1d(in_channels, c3_ch, kernel_size=3, padding=1)
            self.conv5 = nn.Conv1d(in_channels, c5_ch, kernel_size=5, padding=2)
            self.conv7 = nn.Conv1d(in_channels, c7_ch, kernel_size=7, padding=3)

            self.bn_conv = nn.BatchNorm1d(conv_channels)
            self.act = nn.GELU()
            self.dropout = nn.Dropout(dropout)

            # Bidirectional LSTM
            self.lstm = nn.LSTM(
                input_size=conv_channels,
                hidden_size=lstm_hidden,
                num_layers=num_lstm_layers,
                batch_first=True,
                bidirectional=True,
                dropout=dropout if num_lstm_layers > 1 else 0.0,
            )

            feat_dim = lstm_hidden * 2

            # Attention-based temporal pooling
            self.attn_query = nn.Linear(feat_dim, 1)

            # Multi-Horizon Prediction Heads
            self.head_15m = nn.Sequential(
                nn.Linear(feat_dim, 64),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(64, 1),
            )
            self.head_30m = nn.Sequential(
                nn.Linear(feat_dim, 64),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(64, 1),
            )
            self.head_60m = nn.Sequential(
                nn.Linear(feat_dim, 64),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(64, 1),
            )
            self.head_mag = nn.Sequential(
                nn.Linear(feat_dim, 64),
                nn.GELU(),
                nn.Linear(64, 1),
            )

        def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
            """
            Args:
                x: (Batch, Seq_Len, In_Channels)
            """
            B, L, C = x.shape
            x_t = x.transpose(1, 2)  # (B, C, L)

            # Multi-scale Convolutions
            c3 = self.conv3(x_t)
            c5 = self.conv5(x_t)
            c7 = self.conv7(x_t)
            c_cat = torch.cat([c3, c5, c7], dim=1)  # (B, conv_channels, L)
            conv_out = self.dropout(self.act(self.bn_conv(c_cat))).transpose(1, 2)  # (B, L, conv_channels)

            # BiLSTM sequence encoding
            lstm_out, _ = self.lstm(conv_out)  # (B, L, 2 * lstm_hidden)

            # Temporal Attention Pooling
            attn_weights = F.softmax(self.attn_query(lstm_out), dim=1)  # (B, L, 1)
            pooled = torch.sum(attn_weights * lstm_out, dim=1)  # (B, feat_dim)

            # Prediction heads
            logits_15m = self.head_15m(pooled).squeeze(-1)
            logits_30m = self.head_30m(pooled).squeeze(-1)
            logits_60m = self.head_60m(pooled).squeeze(-1)
            pred_mag = F.relu(self.head_mag(pooled).squeeze(-1))

            return {
                "logits_15m": logits_15m,
                "logits_30m": logits_30m,
                "logits_60m": logits_60m,
                "pred_mag": pred_mag,
                "attn_weights": attn_weights,
            }


    # ==============================================================================
    # 3. Architecture 2: Spatio-Temporal Graph Transformer
    # ==============================================================================

    class MultiDetectorSpatialGraphLayer(nn.Module):
        """Cross-node spatial graph attention across Aditya-L1 detector channels:
        Node 0: SoLEXS SDD1 (Soft X-Ray primary)
        Node 1: SoLEXS SDD2 (Soft X-Ray backup)
        Node 2: HEL1OS Band 1 (Hard X-Ray 10-20 keV)
        Node 3: HEL1OS Band 2 (Hard X-Ray 20-50 keV)
        Node 4: Neupert Physics Coupling
        """
        def __init__(self, num_nodes: int = 5, node_dim: int = 32, nheads: int = 4):
            super().__init__()
            self.num_nodes = num_nodes
            self.node_dim = node_dim
            self.spatial_attn = nn.MultiheadAttention(
                embed_dim=node_dim,
                num_heads=nheads,
                batch_first=True,
            )
            self.norm = nn.LayerNorm(node_dim)
            self.ffn = nn.Sequential(
                nn.Linear(node_dim, node_dim * 2),
                nn.GELU(),
                nn.Linear(node_dim * 2, node_dim),
            )
            self.norm_ffn = nn.LayerNorm(node_dim)

        def forward(self, node_feats: torch.Tensor) -> torch.Tensor:
            """
            Args:
                node_feats: (Batch * Time, Num_Nodes, Node_Dim)
            """
            attn_out, _ = self.spatial_attn(node_feats, node_feats, node_feats)
            x = self.norm(node_feats + attn_out)
            out = self.norm_ffn(x + self.ffn(x))
            return out


    class SpatioTemporalGraphTransformer(nn.Module):
        """Spatio-Temporal Graph Transformer for Aditya-L1 Solar Flare Forecasting."""
        def __init__(
            self,
            num_nodes: int = 5,
            in_features_per_node: int = 2,
            d_model: int = 64,
            nhead: int = 4,
            num_temporal_layers: int = 3,
            dropout: float = 0.1,
            max_seq_len: int = 500,
        ):
            super().__init__()
            self.num_nodes = num_nodes
            self.d_model = d_model

            # Node feature projection
            self.node_proj = nn.Linear(in_features_per_node, 32)

            # Spatial Graph Attention
            self.spatial_graph = MultiDetectorSpatialGraphLayer(num_nodes=num_nodes, node_dim=32, nheads=4)

            # Fuse nodes -> temporal token
            self.fuse_nodes = nn.Linear(num_nodes * 32, d_model)

            # Positional encoding
            self.pos_encoder = nn.Parameter(torch.randn(1, max_seq_len, d_model) * 0.02)

            # Temporal Transformer Encoder
            enc_layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=d_model * 4,
                dropout=dropout,
                batch_first=True,
                activation="gelu",
            )
            self.temporal_transformer = nn.TransformerEncoder(enc_layer, num_layers=num_temporal_layers)

            # Residual Temporal Shortcut (Direct conv skip connection)
            self.residual_conv = nn.Conv1d(num_nodes * in_features_per_node, d_model, kernel_size=1)

            # Physics PINN parameter estimation head
            self.pinn_head = nn.Sequential(
                nn.Linear(d_model, 32),
                nn.GELU(),
                nn.Linear(32, 1),  # predicts dSXR/dt
            )
            # Learned PINN thermodynamic coefficients (alpha: heating, beta: cooling)
            self.learned_alpha = nn.Parameter(torch.tensor(0.18, dtype=torch.float32))
            self.learned_beta = nn.Parameter(torch.tensor(0.04, dtype=torch.float32))

            # Calibrated Multi-Horizon Classification Heads
            self.head_15m = nn.Sequential(
                nn.Linear(d_model, 32),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(32, 1)
            )
            self.head_30m = nn.Sequential(
                nn.Linear(d_model, 32),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(32, 1)
            )
            self.head_60m = nn.Sequential(
                nn.Linear(d_model, 32),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(32, 1)
            )

            # Calibrated Temperature scaling parameter
            self.temperature = nn.Parameter(torch.ones(1) * 1.0)

            self.head_mag = nn.Sequential(nn.Linear(d_model, 64), nn.GELU(), nn.Linear(64, 1))

        def forward(self, graph_seq: torch.Tensor) -> Dict[str, torch.Tensor]:
            """
            Args:
                graph_seq: (Batch, Seq_Len, Num_Nodes, In_Features_Per_Node)
            """
            B, L, N, F_dim = graph_seq.shape

            # 1. Project node features: (B * L, N, 32)
            flat_nodes = graph_seq.view(B * L, N, F_dim)
            proj_nodes = self.node_proj(flat_nodes)

            # 2. Spatial Graph Message Passing: (B * L, N, 32)
            graph_out = self.spatial_graph(proj_nodes)

            # 3. Fuse nodes to form temporal representation: (B, L, d_model)
            temporal_tokens = self.fuse_nodes(graph_out.view(B, L, N * 32))
            temporal_tokens = temporal_tokens + self.pos_encoder[:, :L, :]

            # 4. Temporal Transformer with Direct Residual Shortcut
            raw_input_flat = graph_seq.view(B, L, N * F_dim).transpose(1, 2)  # (B, N*F, L)
            res_shortcut = self.residual_conv(raw_input_flat).transpose(1, 2) # (B, L, d_model)
            
            transformer_out = self.temporal_transformer(temporal_tokens)
            latents = transformer_out + 0.2 * res_shortcut  # (B, L, d_model)

            # 5. Attention-weighted Latent Pooling
            pooled = 0.6 * latents[:, -1, :] + 0.4 * torch.mean(latents, dim=1)

            # 6. Temperature-Calibrated Outputs
            temp = torch.clamp(self.temperature, min=0.1, max=5.0)
            logits_15m = (self.head_15m(pooled).squeeze(-1)) / temp
            logits_30m = (self.head_30m(pooled).squeeze(-1)) / temp
            logits_60m = (self.head_60m(pooled).squeeze(-1)) / temp
            pred_mag = F.relu(self.head_mag(pooled).squeeze(-1))
            dsxr_dt_pred = self.pinn_head(latents[:, -1, :]).squeeze(-1)

            return {
                "logits_15m": logits_15m,
                "logits_30m": logits_30m,
                "logits_60m": logits_60m,
                "pred_mag": pred_mag,
                "dsxr_dt_pred": dsxr_dt_pred,
                "alpha": torch.clamp(self.learned_alpha, min=0.01, max=1.0),
                "beta": torch.clamp(self.learned_beta, min=0.001, max=0.5),
            }


    # ==============================================================================
    # 4. PyTorch Dataset & DataLoader
    # ==============================================================================

    class SpaceWeatherDataset(Dataset):
        """Multi-modal sliding window dataset for Aditya-L1 flare precursor forecasting."""
        def __init__(
            self,
            features_2d: np.ndarray,
            graph_4d: np.ndarray,
            labels_15m: np.ndarray,
            labels_30m: np.ndarray,
            labels_60m: np.ndarray,
            mags: np.ndarray,
            times_sec: Optional[np.ndarray] = None,
            window_len: int = 60,
        ):
            self.feat_2d = torch.tensor(features_2d, dtype=torch.float32)
            self.graph_4d = torch.tensor(graph_4d, dtype=torch.float32)
            self.labels_15m = torch.tensor(labels_15m, dtype=torch.float32)
            self.labels_30m = torch.tensor(labels_30m, dtype=torch.float32)
            self.labels_60m = torch.tensor(labels_60m, dtype=torch.float32)
            self.mags = torch.tensor(mags, dtype=torch.float32)
            self.times_sec = torch.tensor(times_sec, dtype=torch.float32) if times_sec is not None else torch.zeros(len(features_2d))
            self.window_len = window_len
            self.length = max(0, len(self.feat_2d) - window_len)

        def __len__(self) -> int:
            return self.length

        def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
            end = idx + self.window_len
            return {
                "feat_seq": self.feat_2d[idx:end],
                "graph_seq": self.graph_4d[idx:end],
                "label_15m": self.labels_15m[end - 1],
                "label_30m": self.labels_30m[end - 1],
                "label_60m": self.labels_60m[end - 1],
                "target_mag": self.mags[end - 1],
                "time_sec": self.times_sec[end - 1],
            }
else:
    class CNNLSTMSolarForecaster:
        pass

    class SpatioTemporalGraphTransformer:
        pass

    class BinaryFocalLoss:
        pass

    class NeupertPhysicsLoss:
        pass

    class SpaceWeatherDataset:
        pass
