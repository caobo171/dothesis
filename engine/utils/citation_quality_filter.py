#!/usr/bin/env python3
"""
ABOUTME: Citation quality filter - removes low-quality citations from database
ABOUTME: Uses enhanced citation validator to filter out invalid/junk citations before compilation
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add parent directory to path for imports
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.citation_validator import CitationValidator, ValidationIssue

# Minimum topical relevance score for a citation to be kept.
# Configurable via CITATION_RELEVANCE_THRESHOLD env var (float 0.0–1.0).
# Default 0.30 — the stop-word list now excludes generic academic noise
# ("approaches", "methodologies", "models", etc.) so the remaining keywords
# are truly discriminating, making 0.30 effectively much stricter than before.
_RELEVANCE_THRESHOLD = float(os.environ.get("CITATION_RELEVANCE_THRESHOLD", "0.30"))

logger = logging.getLogger(__name__)

# Common stop words to exclude from topic keyword extraction
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall", "its", "it", "this",
    "that", "these", "those", "how", "what", "which", "who", "whom", "when",
    "where", "why", "not", "no", "nor", "so", "if", "then", "than", "too",
    "very", "just", "about", "above", "after", "again", "all", "also", "any",
    "as", "between", "both", "each", "few", "more", "most", "other", "over",
    "same", "some", "such", "through", "under", "up", "out", "into", "using",
    "based", "via", "across", "among", "during", "within", "without",
    "research", "study", "analysis", "review", "paper", "approach", "new",
    "role", "impact", "effect", "effects", "use", "case", "toward", "towards",
    # Generic academic phrasing that adds noise without being discriminating.
    # Only include words that are unlikely to be the primary discriminating
    # keyword for any real research topic (section headings, meta-language, etc.)
    "approaches", "methodologies", "methodology", "including", "current",
    "solving", "overview", "introduction", "discussion", "implications",
    "findings", "conclusion", "conclusions", "importance", "comparison",
    "recent", "existing", "proposed", "novel", "improved", "enhanced",
    "advanced", "multiple", "various", "different", "specific", "given",
    "related", "relevant",
})

# Synonym clusters for academic domain matching.
# Each cluster groups terms that are interchangeable in academic context.
# When a topic keyword matches any term in a cluster, ALL terms in that cluster
# are used for matching against citation text.
_SYNONYM_CLUSTERS: List[frozenset] = [
    # LLM / Language Models (specific — gpt, llama, etc.)
    # Separate from general AI so "AI Management Standard" topics don't match LLM-specific queries.
    frozenset({"llm", "large language model", "large language models",
               "language model", "language models",
               "gpt", "gpt-4", "gpt-3", "gpt4", "gpt3", "gpt-3.5", "chatgpt",
               "claude", "gemini", "llama", "mistral", "falcon", "palm",
               "bert", "t5", "bart", "roberta", "foundation model", "foundation models",
               "instruction-tuned", "instruction tuning", "fine-tuned language model",
               "pretrained language model", "autoregressive model"}),
    # General AI / ML (broader — ai, ml, deep learning, reinforcement learning)
    frozenset({"ai", "artificial intelligence", "machine learning", "ml", "deep learning",
               "neural network", "neural networks", "computer vision", "nlp",
               "natural language processing", "reinforcement learning",
               "transformer", "transformers", "generative ai", "gen ai"}),
    # Reward / RLHF (for reward-model topics)
    # NOTE: "verify"/"verification" intentionally excluded — too generic (auth, QA, crypto).
    # "step by step" excluded — too generic (tutorials, guides, any how-to content).
    frozenset({"reward", "reward model", "reward models", "reward signal", "reward function",
               "rlhf", "reinforcement learning from human feedback",
               "preference learning", "preference optimization",
               "dpo", "ppo", "proximal policy optimization",
               "scorer", "scoring", "human feedback", "process reward",
               "outcome reward", "critic model", "preference data",
               "reward shaping", "reward modeling"}),
    # Reasoning / Chain-of-Thought (for reasoning-focused topics)
    # NOTE: "step by step" and "step-by-step" excluded — too generic (tutorials, KYC guides, etc.)
    # NOTE: "inference" excluded — polysemous (ML inference != logical inference != reasoning)
    frozenset({"reasoning", "chain of thought", "chain-of-thought", "cot",
               "multi-step reasoning", "logical reasoning", "mathematical reasoning",
               "commonsense reasoning", "commonsense", "common sense",
               "deduction", "deductive", "induction", "inductive",
               "problem solving", "problem-solving", "planning",
               "tree of thought", "tree-of-thought", "tot",
               "self-consistency", "rationale", "rationales"}),
    # Healthcare / Medicine
    frozenset({"healthcare", "health care", "medical", "medicine", "clinical",
               "biomedical", "health", "patient", "patients", "diagnosis",
               "therapeutic", "therapy", "treatment", "disease", "diseases",
               "pathology", "epidemiology", "pharmaceutical", "pharmacology"}),
    # Environment / Climate
    frozenset({"environment", "environmental", "climate", "climate change",
               "global warming", "sustainability", "sustainable", "ecology",
               "ecological", "carbon", "emissions", "greenhouse",
               "renewable energy", "green energy", "pollution"}),
    # Education / Learning
    frozenset({"education", "educational", "learning", "teaching", "pedagogy",
               "pedagogical", "student", "students", "curriculum", "academic",
               "classroom", "instruction", "instructional", "e-learning",
               "elearning", "online learning"}),
    # Security / Cyber
    frozenset({"security", "cybersecurity", "cyber security", "infosec",
               "information security", "encryption", "cryptography",
               "vulnerability", "vulnerabilities", "malware", "threat",
               "threats", "intrusion", "authentication", "privacy"}),
    # Finance / Economics
    frozenset({"finance", "financial", "economics", "economic", "banking",
               "investment", "market", "markets", "monetary", "fiscal",
               "stock", "trading", "fintech", "cryptocurrency", "blockchain"}),
    # IoT / Embedded
    frozenset({"iot", "internet of things", "embedded", "sensor", "sensors",
               "smart device", "smart devices", "wearable", "wearables",
               "edge computing", "fog computing", "mqtt", "microcontroller"}),
    # Robotics / Automation
    frozenset({"robot", "robots", "robotics", "automation", "autonomous",
               "actuator", "manipulator", "drone", "drones", "uav"}),
    # Data / Analytics
    frozenset({"data", "big data", "data science", "analytics", "data mining",
               "data analysis", "database", "databases", "data warehouse",
               "visualization", "statistical", "statistics"}),
    # Network / Communication
    frozenset({"network", "networks", "networking", "wireless", "wifi",
               "cellular", "5g", "telecommunications", "communication",
               "protocol", "protocols", "bandwidth", "latency", "routing"}),
    # Ethics / Bias
    frozenset({"ethics", "ethical", "bias", "fairness", "accountability",
               "transparency", "responsible", "discrimination", "equity",
               "justice", "moral"}),
    # Cloud / Infrastructure
    frozenset({"cloud", "cloud computing", "saas", "paas", "iaas",
               "serverless", "microservices", "containerization", "docker",
               "kubernetes", "devops", "infrastructure"}),
    # Integrity / Fraud
    frozenset({"integrity", "fraud", "forgery", "counterfeit", "falsification",
               "plagiarism", "misconduct", "fabrication", "deception",
               "authenticity", "verification", "detection"}),
    # Energy / Power
    frozenset({"energy", "power", "solar", "wind", "battery", "batteries",
               "photovoltaic", "grid", "electricity", "renewable",
               "nuclear", "fossil fuel", "geothermal"}),
    # Psychology / Mental Health
    frozenset({"psychology", "psychological", "mental health", "cognitive",
               "cognition", "behavior", "behaviour", "behavioral",
               "behavioural", "anxiety", "depression", "stress",
               "well-being", "wellbeing", "neuroscience"}),
    # Agriculture / Food
    frozenset({"agriculture", "agricultural", "farming", "crop", "crops",
               "soil", "irrigation", "livestock", "food security",
               "agronomy", "horticulture", "precision agriculture"}),
    # Sleep / Circadian
    frozenset({"sleep", "insomnia", "circadian", "melatonin", "polysomnography",
               "sleep quality", "sleep disorder", "sleep disorders", "rem",
               "sleep deprivation", "somnolence", "narcolepsy"}),
    # Performance / Productivity
    frozenset({"performance", "productivity", "achievement", "outcome", "outcomes",
               "efficiency", "effectiveness", "competence", "proficiency",
               "academic performance", "grade", "grades", "gpa"}),
    # Social Media / Digital
    frozenset({"social media", "facebook", "twitter", "instagram", "tiktok",
               "digital", "online", "internet", "platform", "platforms",
               "social network", "social networks", "influencer", "viral"}),
    # Business / Management
    frozenset({"business", "management", "organization", "organizational",
               "leadership", "corporate", "enterprise", "strategy", "strategic",
               "governance", "stakeholder", "stakeholders", "supply chain"}),
    # Transportation / Mobility
    frozenset({"transport", "transportation", "mobility", "traffic", "vehicle",
               "vehicles", "autonomous driving", "self-driving", "logistics",
               "rail", "aviation", "urban mobility"}),
]

# Build lookup: single keyword -> set of all synonyms in its cluster
_SYNONYM_LOOKUP: Dict[str, frozenset] = {}
for _cluster in _SYNONYM_CLUSTERS:
    for _term in _cluster:
        _SYNONYM_LOOKUP[_term] = _cluster


def _expand_with_synonyms(keywords: Set[str]) -> Set[str]:
    """Expand keywords with synonyms from known academic clusters."""
    expanded = set(keywords)
    for kw in keywords:
        if kw in _SYNONYM_LOOKUP:
            expanded.update(_SYNONYM_LOOKUP[kw])
    return expanded


def _extract_topic_keywords(topic: str) -> Set[str]:
    """Extract meaningful keywords from the paper topic."""
    words = re.findall(r'[a-z]{2,}', topic.lower())
    return {w for w in words if w not in _STOP_WORDS}


def _compute_relevance_score(topic_keywords: Set[str], title: str, abstract: str) -> float:
    """
    Compute topical relevance score (0.0 to 1.0) based on keyword overlap.

    Expands keywords with synonyms so "AI" matches "machine learning",
    "healthcare" matches "medical", etc.

    Title matches are weighted at 1.0, abstract-only matches at 0.5,
    so citations whose titles mention the topic rank higher.
    """
    if not topic_keywords:
        return 1.0  # No keywords to check against, assume relevant
    title_lower = title.lower()
    abstract_lower = abstract.lower()

    score = 0.0
    max_score = len(topic_keywords)
    for kw in topic_keywords:
        # Title match is worth 1.0, abstract-only match is worth 0.5
        if kw in title_lower:
            score += 1.0
            continue
        cluster = _SYNONYM_LOOKUP.get(kw)
        if cluster and any(syn in title_lower for syn in cluster):
            score += 1.0
            continue
        # Fallback to abstract match (half weight)
        if kw in abstract_lower:
            score += 0.5
            continue
        if cluster and any(syn in abstract_lower for syn in cluster):
            score += 0.5

    return score / max_score


class CitationQualityFilter:
    """Filters low-quality citations from citation database."""

    def __init__(self, strict_mode: bool = True):
        """
        Initialize filter.

        Args:
            strict_mode: If True, filter all critical issues. If False, only filter worst offenders.
        """
        self.validator = CitationValidator()
        self.strict_mode = strict_mode

    def should_filter_citation(self, issues: List[ValidationIssue]) -> Tuple[bool, str]:
        """
        Determine if a citation should be filtered out.

        Args:
            issues: List of validation issues for this citation

        Returns:
            Tuple of (should_filter: bool, reason: str)
        """
        if not issues:
            return False, ""

        # Critical issues that ALWAYS result in filtering
        critical_filters = [
            'invalid_url',         # HTTP 403, 404, 500 errors
            'invalid_metadata',    # Domain as author/title, error keywords
        ]

        # In strict mode, filter ALL critical issues
        if self.strict_mode:
            critical = [i for i in issues if i.severity == 'critical']
            if critical:
                reasons = [i.message for i in critical[:3]]  # Show first 3
                return True, "; ".join(reasons)

        # In non-strict mode, only filter specific critical issues
        for issue in issues:
            if issue.issue_type in critical_filters:
                return True, issue.message

        return False, ""

    def filter_database(
        self,
        database_path: Path,
        output_path: Path = None,
        topic: Optional[str] = None,
    ) -> Dict:
        """
        Filter low-quality citations from database.

        Args:
            database_path: Path to citation_database.json
            output_path: Path to save filtered database (default: same as input)
            topic: Paper topic string for topical relevance filtering

        Returns:
            Dict with filtering statistics
        """
        # Load database
        with open(database_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in {database_path}: {e}")
                return {
                    'total_original': 0, 'total_filtered': 0,
                    'total_removed': 0, 'removal_reasons': {},
                }

        original_count = len(data.get('citations', []))
        citations = data.get('citations', [])

        print(f"🔍 Filtering {original_count} citations from {database_path.name}...")

        # Validate and filter
        filtered_citations = []
        removed_citations = []
        filter_stats = {
            'total_original': original_count,
            'total_filtered': 0,
            'total_removed': 0,
            'removal_reasons': {}
        }

        for citation in citations:
            issues = self.validator.validate_citation(citation)
            should_filter, reason = self.should_filter_citation(issues)

            if should_filter:
                removed_citations.append({
                    'citation': citation,
                    'reason': reason,
                    'issues': len(issues)
                })
                filter_stats['total_removed'] += 1

                # Track removal reasons
                issue_type = issues[0].issue_type if issues else 'unknown'
                filter_stats['removal_reasons'][issue_type] = \
                    filter_stats['removal_reasons'].get(issue_type, 0) + 1
            else:
                filtered_citations.append(citation)

        # Topical relevance filtering: remove citations with zero keyword overlap
        # Only apply when topic has enough keywords to be meaningful (2+)
        if topic:
            topic_keywords = _extract_topic_keywords(topic)
            if len(topic_keywords) >= 2:
                relevance_filtered = []
                off_topic_count = 0
                for citation in filtered_citations:
                    title = citation.get('title', '')
                    abstract = citation.get('abstract', '')
                    score = _compute_relevance_score(topic_keywords, title, abstract)
                    if score >= _RELEVANCE_THRESHOLD:
                        relevance_filtered.append(citation)
                    else:
                        off_topic_count += 1
                        removed_citations.append({
                            'citation': citation,
                            'reason': f'Low topical relevance (score={score:.2f}, threshold={_RELEVANCE_THRESHOLD:.2f})',
                            'issues': 0,
                        })
                        filter_stats['total_removed'] += 1
                        filter_stats['removal_reasons']['low_relevance'] = \
                            filter_stats['removal_reasons'].get('low_relevance', 0) + 1
                        logger.info(
                            f"Filtered low-relevance citation: {citation.get('title', '')[:80]} "
                            f"(relevance={score:.2f})"
                        )
                if off_topic_count:
                    logger.info(
                        f"Topical filter: removed {off_topic_count} off-topic citations "
                        f"(threshold={_RELEVANCE_THRESHOLD:.2f}, kept={len(relevance_filtered)})"
                    )
                filtered_citations = relevance_filtered

        filter_stats['total_filtered'] = len(filtered_citations)

        # Update database with filtered citations
        data['citations'] = filtered_citations

        # CRITICAL: Update metadata citation count to match filtered count
        # Field name MUST match CitationDatabase.to_dict() which uses "total_citations"
        if 'metadata' in data:
            data['metadata']['total_citations'] = len(filtered_citations)

        # Save filtered database
        if output_path is None:
            output_path = database_path

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Save removal report
        report_path = output_path.parent / f"{output_path.stem}_removal_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'stats': filter_stats,
                'removed_citations': removed_citations
            }, f, indent=2, ensure_ascii=False)

        return filter_stats

    def generate_report(self, stats: Dict, database_name: str) -> str:
        """
        Generate human-readable filtering report.

        Args:
            stats: Statistics from filter_database()
            database_name: Name of database for report

        Returns:
            Formatted report string
        """
        report = [f"\n{'='*80}"]
        report.append(f"CITATION QUALITY FILTER REPORT: {database_name}")
        report.append(f"{'='*80}\n")

        report.append(f"Original citations:  {stats['total_original']}")
        report.append(f"Filtered (kept):     {stats['total_filtered']} ✅")
        report.append(f"Removed (filtered):  {stats['total_removed']} ❌")

        if stats['total_original'] > 0:
            kept_pct = (stats['total_filtered'] / stats['total_original']) * 100
            removed_pct = (stats['total_removed'] / stats['total_original']) * 100
            report.append(f"\nRetention rate:      {kept_pct:.1f}%")
            report.append(f"Removal rate:        {removed_pct:.1f}%")

        if stats['removal_reasons']:
            report.append(f"\n--- Removal Breakdown ---")
            for reason, count in sorted(stats['removal_reasons'].items(),
                                       key=lambda x: x[1], reverse=True):
                report.append(f"  {reason:25s}: {count} citations")

        report.append(f"\n{'='*80}\n")

        return '\n'.join(report)


def main():
    """Main entry point for CLI filtering."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Filter low-quality citations from citation database'
    )
    parser.add_argument(
        'database',
        type=Path,
        help='Path to citation_database.json'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output path (default: overwrite input)'
    )
    parser.add_argument(
        '--lenient',
        action='store_true',
        help='Lenient mode (only filter worst offenders)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be filtered without modifying files'
    )

    args = parser.parse_args()

    if not args.database.exists():
        print(f"❌ Error: Database not found: {args.database}")
        return 1

    # Create filter
    filter_obj = CitationQualityFilter(strict_mode=not args.lenient)

    # Dry run: validate and show stats without filtering
    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be modified\n")
        with open(args.database, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON in {args.database}: {e}")
                return 1

        validator = CitationValidator()
        to_remove = 0

        for citation in data.get('citations', []):
            issues = validator.validate_citation(citation)
            should_filter, reason = filter_obj.should_filter_citation(issues)
            if should_filter:
                to_remove += 1

        print(f"Would remove: {to_remove}/{len(data.get('citations', []))} citations")
        return 0

    # Actual filtering
    stats = filter_obj.filter_database(args.database, args.output)
    report = filter_obj.generate_report(stats, args.database.name)

    print(report)

    if stats['total_removed'] > 0:
        print(f"💾 Filtered database saved to: {args.output or args.database}")
        print(f"📊 Removal report saved to: {(args.output or args.database).parent / f'{args.database.stem}_removal_report.json'}")

    return 0


if __name__ == '__main__':
    exit(main())
