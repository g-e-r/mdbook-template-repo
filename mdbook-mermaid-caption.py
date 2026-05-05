#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.14"
# dependencies = [
# ]
# ///
"""mdbook preprocessor: transforms ```mermaid <caption> into <figure> with auto-numbered figcaption."""
import json
import re
import sys
from typing import Dict, Any, List, Match, Optional

if len(sys.argv) > 1 and sys.argv[1] == "supports":
    sys.exit(0)

# ============================================================================
# Regular Expression Patterns
# ============================================================================

DIAGRAM_PATTERN = re.compile(
    r'```(mermaid|d2) ([^\n]+)\n(.*?)```',
    flags=re.DOTALL
)

SVG_PATTERN = re.compile(
    r'!\[([^\]]+)\]\(([^)]+\.svg)\)'
)

# ============================================================================
# Figure Counter
# ============================================================================

class FigureCounter:
    """Manages automatic figure numbering."""
    
    def __init__(self):
        """Initialize counter at 0."""
        self.count = 0
    
    def next(self) -> int:
        """Get next figure number and increment counter."""
        self.count += 1
        return self.count
    
    def reset(self) -> None:
        """Reset counter to 0."""
        self.count = 0

# ============================================================================
# Figure Generation
# ============================================================================

class DiagramReplacer:
    """Handles replacement of diagram code blocks with figures."""
    
    def __init__(self, counter: FigureCounter):
        """Initialize with a figure counter."""
        self.counter = counter
    
    def replace(self, match: Match) -> str:
        """Replace diagram code block with figure element."""
        lang = match.group(1)
        caption = match.group(2).strip()
        body = match.group(3)
        
        if not caption:
            return match.group(0)
        
        fig_num = self.counter.next()
        return (
            f'<figure>\n\n'
            f'```{lang}\n{body}```\n\n'
            f'<figcaption>図{fig_num}: {caption}</figcaption>\n'
            f'</figure>'
        )


class SVGReplacer:
    """Handles replacement of SVG image references with figures."""
    
    def __init__(self, counter: FigureCounter):
        """Initialize with a figure counter."""
        self.counter = counter
    
    def replace(self, match: Match) -> str:
        """Replace SVG image with figure element."""
        caption = match.group(1).strip()
        path = match.group(2)
        
        if not caption or not path.endswith('.svg'):
            return match.group(0)
        
        fig_num = self.counter.next()
        return (
            f'<figure>\n\n'
            f'![{caption}]({path})\n\n'
            f'<figcaption>図{fig_num}: {caption}</figcaption>\n'
            f'</figure>'
        )

# ============================================================================
# Content Processing
# ============================================================================

class ContentProcessor:
    """Processes markdown content to add figures and captions."""
    
    def __init__(self, counter: FigureCounter):
        """Initialize with a figure counter."""
        self.counter = counter
        self.diagram_replacer = DiagramReplacer(counter)
        self.svg_replacer = SVGReplacer(counter)
    
    def process(self, content: str) -> str:
        """
        Process content to transform diagrams and SVGs into figures.
        
        Args:
            content: Markdown content to process
            
        Returns:
            Processed content with figures
        """
        # Find all matches
        diagram_matches = list(DIAGRAM_PATTERN.finditer(content))
        svg_matches = list(SVG_PATTERN.finditer(content))
        
        # Combine and sort by start position
        all_matches = [('diagram', match) for match in diagram_matches] + [('svg', match) for match in svg_matches]
        all_matches.sort(key=lambda x: x[1].start())
        
        # Process in order
        result = []
        last_end = 0
        for type_, match in all_matches:
            result.append(content[last_end:match.start()])
            if type_ == 'diagram':
                replacement = self.diagram_replacer.replace(match)
            else:
                replacement = self.svg_replacer.replace(match)
            result.append(replacement)
            last_end = match.end()
        result.append(content[last_end:])
        
        return ''.join(result)

# ============================================================================
# Book Walking
# ============================================================================

class BookWalker:
    """Walks through book structure and processes chapters."""
    
    def __init__(self, processor: ContentProcessor):
        """Initialize with a content processor."""
        self.processor = processor
    
    def walk(self, items: List[Dict[str, Any]]) -> None:
        """
        Recursively walk through book items and process chapter content.
        
        Args:
            items: List of book items to process
        """
        for item in items:
            if not isinstance(item, dict):
                continue
            
            chapter = item.get("Chapter")
            if not chapter:
                continue
            
            # Process chapter content
            chapter["content"] = self.processor.process(chapter["content"])
            
            # Recursively process sub-items
            self.walk(chapter.get("sub_items", []))

# ============================================================================
# Main Execution
# ============================================================================

def main():
    """Main entry point for the mdbook preprocessor."""
    context, book = json.load(sys.stdin)
    
    # Initialize components
    counter = FigureCounter()
    processor = ContentProcessor(counter)
    walker = BookWalker(processor)
    
    # Process all chapters
    walker.walk(book["items"])
    
    # Output result
    print(json.dumps(book))


if __name__ == "__main__":
    main()
