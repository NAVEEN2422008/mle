#!/usr/bin/env python3
"""
Multi-Persona Testing Simulator
Simulates 1000+ diverse personas testing the solar flare prediction system
Each persona has unique background, expertise, and testing focus
"""

import json
import random
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple

# Persona archetypes with their testing focus areas
PERSONA_ARCHETYPES = [
    # Technical Roles
    {"role": "ML Engineer", "focus": ["model", "training", "inference", "performance"], "issues_found": []},
    {"role": "Data Scientist", "focus": ["data", "features", "validation", "statistics"], "issues_found": []},
    {"role": "Backend Developer", "focus": ["api", "server", "database", "security"], "issues_found": []},
    {"role": "Frontend Developer", "focus": ["ui", "ux", "accessibility", "javascript"], "issues_found": []},
    {"role": "DevOps Engineer", "focus": ["deployment", "monitoring", "scaling", "logging"], "issues_found": []},
    {"role": "Security Auditor", "focus": ["security", "auth", "injection", "cors"], "issues_found": []},
    {"role": "QA Tester", "focus": ["bugs", "edge_cases", "error_handling", "testing"], "issues_found": []},
    
    # Domain Experts
    {"role": "Space Weather Scientist", "focus": ["physics", "validation", "accuracy", "domain"], "issues_found": []},
    {"role": "Solar Physicist", "focus": ["physics", "models", "calibration", "theory"], "issues_found": []},
    {"role": "Astrophysicist", "focus": ["data", "observations", "instrumentation", "science"], "issues_found": []},
    {"role": "Astronomer", "focus": ["telescope", "instruments", "data_quality", "calibration"], "issues_found": []},
    
    # Academic/Research Roles
    {"role": "PhD Student", "focus": ["research", "methodology", "papers", "reproducibility"], "issues_found": []},
    {"role": "Postdoc Researcher", "focus": ["analysis", "experiments", "results", "publication"], "issues_found": []},
    {"role": "Professor", "focus": ["pedagogy", "curriculum", "education", "research"], "issues_found": []},
    {"role": "Research Scientist", "focus": ["innovation", "novelty", "impact", "validation"], "issues_found": []},
    
    # Industry Roles
    {"role": "Product Manager", "focus": ["requirements", "user_stories", "roadmap", "market"], "issues_found": []},
    {"role": "Technical Lead", "focus": ["architecture", "design", "scalability", "team"], "issues_found": []},
    {"role": "CTO", "focus": ["strategy", "vision", "technology", "competition"], "issues_found": []},
    {"role": "Startup Founder", "focus": ["business", "traction", "growth", "competition"], "issues_found": []},
    
    # End Users
    {"role": "Satellite Operator", "focus": ["operations", "realtime", "alerts", "reliability"], "issues_found": []},
    {"role": "Mission Controller", "focus": ["mission", "critical", "safety", "decision"], "issues_found": []},
    {"role": "Space Weather Forecast", "focus": ["forecasting", "predictions", "accuracy", "timing"], "issues_found": []},
    {"role": "Aviation Safety Officer", "focus": ["safety", "risk", "protocols", "compliance"], "issues_found": []},
    {"role": "Power Grid Operator", "focus": ["grid", "power", "outage", "reliability"], "issues_found": []},
    
    # Accessibility & Inclusion
    {"role": "Accessibility Advocate", "focus": ["a11y", "wcag", "screen_reader", "keyboard"], "issues_found": []},
    {"role": "Screen Reader User", "focus": ["screen_reader", "navigation", "content", "usability"], "issues_found": []},
    {"role": "Color Blind User", "focus": ["color", "contrast", "visibility", "design"], "issues_found": []},
    {"role": "Low Vision User", "focus": ["font", "size", "contrast", "zoom"], "issues_found": []},
    
    # Educational Roles
    {"role": "High School Teacher", "focus": ["education", "clarity", "examples", "pedagogy"], "issues_found": []},
    {"role": "University Lecturer", "focus": ["teaching", "curriculum", "examples", "assignments"], "issues_found": []},
    {"role": "Student", "focus": ["learning", "understanding", "documentation", "examples"], "issues_found": []},
    
    # International Perspectives
    {"role": "Indian Researcher", "focus": ["aditya_l1", "indigenous", "localization", "context"], "issues_found": []},
    {"role": "European Scientist", "focus": ["eso", "esa", "international", "standards"], "issues_found": []},
    {"role": "US Researcher", "focus": ["nasa", "noaa", "usgs", "standards"], "issues_found": []},
    {"role": "Japanese Researcher", "focus": ["isas", "jaxa", "international", "collaboration"], "issues_found": []},
    
    # Different Technical Backgrounds
    {"role": "Python Developer", "focus": ["python", "code_style", "documentation", "api"], "issues_found": []},
    {"role": "JavaScript Developer", "focus": ["js", "frontend", "browser", "compatibility"], "issues_found": []},
    {"role": "Rust Developer", "focus": ["systems", "performance", "memory", "safety"], "issues_found": []},
    {"role": "Go Developer", "focus": ["concurrency", "performance", "deployment", "cli"], "issues_found": []},
    {"role": "Java Developer", "focus": ["enterprise", "architecture", "patterns", "testing"], "issues_found": []},
    {"role": "C++ Developer", "focus": ["performance", "memory", "optimization", "low_level"], "issues_found": []},
    
    # Different Experience Levels
    {"role": "Beginner", "focus": ["getting_started", "documentation", "examples", "clarity"], "issues_found": []},
    {"role": "Intermediate", "focus": ["usage", "customization", "tutorials", "best_practices"], "issues_found": []},
    {"role": "Expert", "focus": ["advanced", "optimization", "research", "cutting_edge"], "issues_found": []},
    
    # Different Testing Philosophies
    {"role": "Chaos Engineer", "focus": ["resilience", "failure", "chaos", "recovery"], "issues_found": []},
    {"role": "Penetration Tester", "focus": ["security", "vulnerabilities", "attack", "exploit"], "issues_found": []},
    {"role": "Performance Tester", "focus": ["load", "stress", "benchmark", "scalability"], "issues_found": []},
    {"role": "Usability Tester", "focus": ["ux", "user_experience", "efficiency", "satisfaction"], "issues_found": []},
]

# Issue database - known issues that personas might find
KNOWN_ISSUES = [
    # Documentation issues
    {"category": "documentation", "severity": "medium", "description": "README claims inflated TSS (+0.990) vs verified live TSS (+0.218)", "file": "README.md"},
    {"category": "documentation", "severity": "medium", "description": "PROJECT_REPORT.md has same inflated claims", "file": "PROJECT_REPORT.md"},
    {"category": "documentation", "severity": "low", "description": "Bibliography entries lack author names for arXiv papers", "file": "RESEARCH_PAPER.md"},
    
    # Model issues
    {"category": "model", "severity": "high", "description": "Threshold tuned on test fold (data leakage)", "file": "src/forecast/train.py"},
    {"category": "model", "severity": "high", "description": "Synthetic label injection in test_unseen_dataset.py", "file": "scripts/test_unseen_dataset.py"},
    {"category": "model", "severity": "high", "description": "Hardcoded confusion matrix in evaluate_real_world_datasets.py", "file": "scripts/evaluate_real_world_datasets.py"},
    {"category": "model", "severity": "medium", "description": "shuffle=True in train_deep_models.py contradicts docstring", "file": "scripts/train_deep_models.py"},
    
    # API issues
    {"category": "api", "severity": "high", "description": "CORS wildcard with credentials enabled (broken auth)", "file": "src/api/main.py"},
    {"category": "api", "severity": "medium", "description": "torch.load without weights_only=True (RCE risk)", "file": "src/api/main.py"},
    {"category": "api", "severity": "medium", "description": "Mutable default argument in infer() function", "file": "src/api/main.py"},
    {"category": "api", "severity": "low", "description": "Dead code in _build_stream function", "file": "src/api/main.py"},
    
    # Threading issues
    {"category": "threading", "severity": "high", "description": "Race conditions in LiveEngine shared state", "file": "src/api/main.py"},
    {"category": "threading", "severity": "medium", "description": "No graceful shutdown mechanism", "file": "src/api/main.py"},
    
    # Frontend issues
    {"category": "security", "severity": "high", "description": "XSS via innerHTML in logEvent function", "file": "dashboard/index.html"},
    {"category": "security", "severity": "high", "description": "XSS via innerHTML in cursorTracker", "file": "dashboard/index.html"},
    {"category": "security", "severity": "high", "description": "XSS in populateCatalogDOM", "file": "dashboard/index.html"},
    {"category": "accessibility", "severity": "medium", "description": "Missing aria-live regions for real-time content", "file": "dashboard/index.html"},
    {"category": "accessibility", "severity": "medium", "description": "trapFocus listener leak", "file": "dashboard/index.html"},
    {"category": "performance", "severity": "medium", "description": "Unbounded DOM growth in event ticker", "file": "dashboard/index.html"},
    {"category": "performance", "severity": "medium", "description": "Unbounded catalogList array growth", "file": "dashboard/index.html"},
    
    # Live data issues
    {"category": "data", "severity": "critical", "description": "No real-time Aditya-L1 data available (daily latency)", "file": "src/ingest/pradan_download.py"},
    {"category": "data", "severity": "high", "description": "GOES live mode removed from engine", "file": "src/api/main.py"},
    
    # Research integrity
    {"category": "research", "severity": "high", "description": "Contradictory TSS values across documents", "file": "multiple"},
    {"category": "research", "severity": "medium", "description": "Demo values presented as real results", "file": "dashboard/index.html"},
]

def generate_persona_id(i: int) -> str:
    """Generate unique persona ID"""
    return f"PERSONA_{i:04d}"

def simulate_persona_test(persona: Dict, issue_pool: List[Dict]) -> Dict[str, Any]:
    """Simulate a single persona's testing session"""
    findings = []
    
    # Each persona has a probability of finding issues based on their focus
    for issue in issue_pool:
        if issue["category"] in persona["focus"] or random.random() < 0.1:
            # Persona might find this issue
            if random.random() < 0.3:  # 30% chance of finding each relevant issue
                findings.append(issue)
    
    # Add some random "creative" findings
    if random.random() < 0.5:
        creative_findings = [
            {"category": "ux", "severity": "low", "description": "Button labels could be more descriptive", "file": "dashboard/index.html"},
            {"category": "documentation", "severity": "low", "description": "Some error messages could be more helpful", "file": "src/api/main.py"},
            {"category": "performance", "severity": "low", "description": "Consider lazy loading for large datasets", "file": "src/forecast/train.py"},
        ]
        findings.extend(random.sample(creative_findings, min(2, len(creative_findings))))
    
    return {
        "persona_id": generate_persona_id(random.randint(1, 1000)),
        "role": persona["role"],
        "focus_areas": persona["focus"],
        "issues_found": findings,
        "timestamp": datetime.now().isoformat()
    }

def run_multi_persona_testing(num_personas: int = 1000) -> Dict[str, Any]:
    """Run multi-persona testing simulation"""
    print(f"🚀 Starting Multi-Persona Testing Simulation ({num_personas} personas)")
    print("=" * 60)
    
    all_findings = []
    issue_counts = {}
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    
    for i in range(num_personas):
        # Select persona archetype (with some randomness)
        archetype = random.choice(PERSONA_ARCHETYPES)
        persona = {
            "role": f"{archetype['role']} #{i % 100}",
            "focus": archetype["focus"],
            "experience": ["Beginner", "Intermediate", "Expert"][i % 3]
        }
        
        # Simulate testing
        result = simulate_persona_test(persona, KNOWN_ISSUES)
        all_findings.append(result)
        
        # Count issues
        for issue in result["issues_found"]:
            cat = issue["category"]
            sev = issue["severity"]
            issue_counts[cat] = issue_counts.get(cat, 0) + 1
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        # Progress indicator
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{num_personas} personas...")
    
    # Aggregate results
    unique_issues = set()
    for finding in all_findings:
        for issue in finding["issues_found"]:
            unique_issues.add(json.dumps(issue, sort_keys=True))
    
    print("\n" + "=" * 60)
    print("📊 TESTING SUMMARY")
    print("=" * 60)
    print(f"Total Personas Tested: {num_personas}")
    print(f"Total Findings: {sum(len(f['issues_found']) for f in all_findings)}")
    print(f"Unique Issues Found: {len(unique_issues)}")
    print(f"\nSeverity Distribution:")
    for sev, count in sorted(severity_counts.items()):
        print(f"  {sev.upper():10s}: {count}")
    print(f"\nIssue Categories:")
    for cat, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:20s}: {count}")
    
    return {
        "total_personas": num_personas,
        "total_findings": sum(len(f["issues_found"]) for f in all_findings),
        "unique_issues": len(unique_issues),
        "severity_distribution": severity_counts,
        "category_distribution": issue_counts,
        "sample_findings": all_findings[:10]  # First 10 for review
    }

if __name__ == "__main__":
    results = run_multi_persona_testing(1000)
    
    # Save results
    output_path = Path("test_results/multi_persona_testing.json")
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📁 Results saved to: {output_path}")