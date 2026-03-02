"""
Policy Document Parser - SSOT for terms, privacy, refund, risk pages and APIs.
Reads markdown files with YAML frontmatter from data/policies/ directory.
"""
import os
import re
import markdown
from typing import Dict, List, Optional
from dataclasses import dataclass


# SSOT Policy directory (relative to project root)
POLICY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "policies")

# Policy type mapping
POLICY_FILES = {
    "terms": "terms.md",
    "privacy": "privacy.md",
    "refund": "refund.md",
    "risk": "risk.md",
    # Aliases for backward compatibility
    "investment_risk": "risk.md",
}


@dataclass
class PolicyDocument:
    """Parsed policy document with metadata and content."""
    type: str
    title: str
    effective_date: str
    version: str
    last_updated: str
    content_md: str  # Raw markdown (without frontmatter)
    content_html: str  # Rendered HTML
    toc: List[Dict[str, str]]  # Table of contents


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from markdown content.
    Returns (metadata_dict, remaining_content).
    """
    if not content.startswith('---'):
        return {}, content

    # Find the closing ---
    end_match = re.search(r'\n---\s*\n', content[3:])
    if not end_match:
        return {}, content

    frontmatter_end = end_match.end() + 3
    frontmatter_text = content[3:end_match.start() + 3]
    remaining_content = content[frontmatter_end:].strip()

    # Parse simple YAML (key: "value" format)
    metadata = {}
    for line in frontmatter_text.strip().split('\n'):
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            metadata[key] = value

    return metadata, remaining_content


def extract_toc(html_content: str) -> tuple[str, List[Dict[str, str]]]:
    """
    Extract TOC from HTML content and add anchor IDs to headings.
    Returns (modified_html, toc_list).
    """
    toc = []

    def add_id_and_toc(match):
        level = match.group(1)
        existing_id = match.group(2) if match.group(2) else None
        inner_html = match.group(3)

        # Strip HTML tags to get text
        text = re.sub(r'<[^>]+>', '', inner_html)

        # Generate ID from text (Korean-friendly)
        heading_id = existing_id or re.sub(r'[^\w가-힣-]', '', text.lower().replace(' ', '-').replace('(', '').replace(')', ''))
        if not heading_id:
            heading_id = f"section-{len(toc)}"

        toc.append({
            'id': heading_id,
            'text': text,
            'depth': int(level)
        })

        return f'<h{level} id="{heading_id}" class="section-anchor"><a href="#{heading_id}" class="heading-link">{inner_html}</a></h{level}>'

    # Process h1 and h2 headings
    modified_html = re.sub(
        r'<h([12])(?:\s+id="([^"]*)")?[^>]*>(.+?)</h\1>',
        add_id_and_toc,
        html_content,
        flags=re.DOTALL
    )

    return modified_html, toc


def parse_policy(policy_type: str) -> Optional[PolicyDocument]:
    """
    Parse a policy document by type.

    Args:
        policy_type: One of 'terms', 'privacy', 'refund', 'risk', 'investment_risk'

    Returns:
        PolicyDocument or None if not found
    """
    # Map to filename
    filename = POLICY_FILES.get(policy_type)
    if not filename:
        return None

    file_path = os.path.join(POLICY_DIR, filename)

    if not os.path.exists(file_path):
        return None

    with open(file_path, 'r', encoding='utf-8') as f:
        raw_content = f.read()

    # Parse frontmatter
    metadata, md_content = parse_frontmatter(raw_content)

    # Convert markdown to HTML
    md = markdown.Markdown(extensions=['tables', 'fenced_code'])
    html_content = md.convert(md_content)

    # Extract TOC and add anchors
    html_with_anchors, toc = extract_toc(html_content)

    # Normalize policy type for response
    normalized_type = policy_type if policy_type != 'investment_risk' else 'risk'

    return PolicyDocument(
        type=normalized_type,
        title=metadata.get('title', ''),
        effective_date=metadata.get('effective_date', ''),
        version=metadata.get('version', ''),
        last_updated=metadata.get('last_updated', ''),
        content_md=md_content,
        content_html=html_with_anchors,
        toc=toc
    )


def get_all_policy_types() -> List[str]:
    """Return list of available policy types."""
    return ['terms', 'privacy', 'refund', 'risk']
