#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "mistune",
# ]
# ///
"""mdbook preprocessor that injects a title page and TOC page."""
import json
import sys
import subprocess
import re
from datetime import date
from collections import defaultdict
from typing import Optional, List, Dict, Tuple, Any

if len(sys.argv) > 1 and sys.argv[1] == "supports":
    sys.exit(0)

# ============================================================================
# Configuration and Constants
# ============================================================================

CHAPTER_TEMPLATE = {
    "number": None,
    "sub_items": [],
    "source_path": None,
    "parent_names": []
}

ID_PATTERN = re.compile(r"\s*\{#([A-Za-z0-9\-_]+)\}\s*$")

# ============================================================================
# Configuration Manager
# ============================================================================

class ConfigManager:
    """Manages configuration extraction from mdbook context."""
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self._book_config = context.get("config", {}).get("book", {})
        self._preproc_config = context.get("config", {}).get("preprocessor", {}).get("toc-page", {})
    
    @property
    def title(self) -> str:
        return self._book_config.get("title", "Document")
    
    @property
    def authors(self) -> List[str]:
        return self._book_config.get("authors", [])
    
    @property
    def author_str(self) -> str:
        return ", ".join(self.authors) if self.authors else ""
    
    @property
    def reviewer(self) -> str:
        return self._preproc_config.get("reviewer", "")
    
    @property
    def approver(self) -> str:
        return self._preproc_config.get("approver", "")
    
    @property
    def src_dir(self) -> str:
        return self._book_config.get("src", "src")
    
    @property
    def today(self) -> str:
        return date.today().strftime("%Y-%m-%d")

# ============================================================================
# Git Operations
# ============================================================================

class GitOperations:
    """Handles git command execution."""
    
    @staticmethod
    def run_command(*args) -> str:
        """Execute a git command and return output."""
        try:
            result = subprocess.check_output(
                ["git"] + list(args),
                stderr=subprocess.DEVNULL
            ).decode().strip()
            return result
        except Exception:
            return ""
    
    @classmethod
    def get_tag(cls) -> str:
        """Get current git tag."""
        return cls.run_command("describe", "--tags", "--always")
    
    @classmethod
    def get_commit_short(cls) -> str:
        """Get short commit hash."""
        return cls.run_command("rev-parse", "--short", "HEAD")
    
    @classmethod
    def get_branch(cls) -> str:
        """Get current branch name."""
        branch = cls.run_command("rev-parse", "--abbrev-ref", "HEAD")
        return branch if branch != "HEAD" else "(detached)"
    
    @classmethod
    def get_dirty_status(cls, src_dir: str) -> bool:
        """Check if source directory has uncommitted changes."""
        return bool(cls.run_command("status", "--porcelain", src_dir))
    
    @classmethod
    def get_version_info(cls, src_dir: str) -> Tuple[str, str, str, str]:
        """Get version, commit, branch, and status information."""
        tag = cls.get_tag()
        commit = cls.get_commit_short()
        branch = cls.get_branch()
        is_dirty = cls.get_dirty_status(src_dir)
        
        version = tag if tag else commit
        status = "DRAFT" if is_dirty else ""
        
        return version, commit, branch, status

# ============================================================================
# History and Changelog Extraction
# ============================================================================

class HistoryExtractor:
    """Extracts git history information."""
    
    @staticmethod
    def get_history(src_dir: str) -> Optional[List[Tuple[str, str, str, str, str, str]]]:
        """
        Extract git history for source directory.
        
        Returns:
            List of (date, sha, tag, author, description, files_str) tuples
        """
        try:
            log = GitOperations.run_command(
                "log",
                "--pretty=format:%h%x09%ad%x09%an%x09%s%x00",
                "--date=short",
                "--",
                src_dir
            )
            
            if not log:
                return None
            
            rows = []
            tag_map = HistoryExtractor._build_tag_map(src_dir)
            
            for entry in log.split("\x00"):
                entry = entry.strip()
                if not entry:
                    continue
                
                parts = entry.split("\t", 3)
                if len(parts) < 3:
                    continue
                
                sha, dt, author = parts[0], parts[1], parts[2]
                body = parts[3].strip() if len(parts) > 3 else ""
                description = body.replace("\n", "<br/>")
                
                files_str = HistoryExtractor._get_files_for_commit(sha, src_dir)
                
                if files_str:
                    tags = ", ".join(tag_map.get(sha, []))
                    rows.append((dt, sha, tags, author, description, files_str))
            
            return rows if rows else None
        except Exception:
            return None
    
    @staticmethod
    def _build_tag_map(src_dir: str) -> Dict[str, List[str]]:
        """Build mapping from commit sha to tags."""
        tag_map = {}
        all_tags = GitOperations.run_command("tag", "-l", "--sort=version:refname").splitlines()
        
        for tag in all_tags:
            latest = GitOperations.run_command("log", tag, "--pretty=format:%h", "-1", "--", src_dir)
            if latest:
                tag_map.setdefault(latest, []).append(tag)
        
        return tag_map
    
    @staticmethod
    def _get_files_for_commit(sha: str, src_dir: str) -> str:
        """Get files changed in commit."""
        try:
            # Check if commit has a parent
            parent_sha = GitOperations.run_command("rev-parse", f"{sha}^")
            if not parent_sha:
                # Initial commit, compare to empty tree
                parent_sha = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
            
            status_out = GitOperations.run_command(
                "-c", "core.quotepath=false",
                "diff-tree", "--no-commit-id", "-r", "--name-status",
                "--relative", parent_sha, sha, "--", src_dir
            )
            status_stripped = [status.replace(src_dir, "", 1) for status in status_out.splitlines()]
            return "<br/>".join(status_stripped) if status_stripped else ""
        except Exception:
            return ""


class ChangelogExtractor:
    """Extracts detailed changelog information."""
    
    @staticmethod
    def get_changelog(src_dir: str) -> Optional[List[Tuple[str, str, str, List, str]]]:
        """
        Extract detailed changelog for source directory.
        
        Returns:
            List of (date, sha, msg, files_list, description) tuples
        """
        try:
            log = GitOperations.run_command(
                "log",
                "--pretty=format:%h%x09%ad%x09%s%x09%B%x00",
                "--date=short",
                "--",
                src_dir
            )
            
            if not log:
                return None
            
            entries = []
            for entry in log.split("\x00"):
                entry = entry.strip()
                if not entry:
                    continue
                
                parts = entry.split("\t", 3)
                if len(parts) < 4:
                    continue
                
                sha, dt, msg, description = parts[0], parts[1], parts[2], parts[3]
                files = ChangelogExtractor._get_file_details(sha, src_dir)
                
                if files:
                    entries.append((dt, sha, msg, files, description))
            
            return entries if entries else None
        except Exception:
            return None
    
    @staticmethod
    def _get_file_details(sha: str, src_dir: str) -> List[Tuple[str, str, Optional[str]]]:
        """Get details about files changed in commit."""
        files = []
        try:
            # Check if commit has a parent
            parent_sha = GitOperations.run_command("rev-parse", f"{sha}^")
            if not parent_sha:
                # Initial commit, compare to empty tree
                parent_sha = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
            
            status_out = GitOperations.run_command(
                "-c", "core.quotepath=false",
                "diff-tree", "--no-commit-id", "-r", "--name-status",
                "--relative", parent_sha, sha, "--", src_dir
            )
            
            if not status_out:
                return files
            
            for line in status_out.splitlines():
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                
                fstatus, fname = parts
                diff = None
                
                if fstatus == "A":
                    files.append(("追加", fname.lstrip(src_dir), None))
                elif fstatus == "D":
                    files.append(("削除", fname.lstrip(src_dir), None))
                elif fstatus.startswith("M"):
                    if fname.endswith(".md"):
                        diff = GitOperations.run_command(
                            "diff", parent_sha, sha, "-U1", "-w", "--", fname
                        )
                    else:
                        diff = None
                    files.append(("変更", fname.lstrip(src_dir), diff))
            
            return files
        except Exception:
            return files

# ============================================================================
# Markdown Processing
# ============================================================================

class MarkdownProcessor:
    """Processes markdown content and extracts heading information."""
    
    def __init__(self):
        import mistune
        self.markdown = mistune.create_markdown(renderer="ast")
    
    def extract_headings(self, md_text: str) -> List[Tuple[int, str, str]]:
        """Extract headings from markdown content."""
        ast = self.markdown(md_text)
        seen = defaultdict(int)
        result = []
        
        self._walk_ast(ast, result, seen)
        return result
    
    def _walk_ast(self, nodes: List[Dict], result: List, seen: Dict[str, int]) -> None:
        """Recursively walk AST and extract heading information."""
        for node in nodes:
            if node["type"] == "heading":
                level = node["attrs"]["level"]
                raw_text = self._extract_text(node.get("children", []))
                text, anchor = self._process_heading(raw_text, seen)
                result.append((level, text, anchor))
            
            if "children" in node:
                self._walk_ast(node["children"], result, seen)
    
    @staticmethod
    def _extract_text(children: List[Dict]) -> str:
        """Extract plain text from AST nodes."""
        parts = []
        for node in children:
            if node["type"] == "text":
                parts.append(node["raw"])
            elif "children" in node:
                parts.append(MarkdownProcessor._extract_text(node["children"]))
        return "".join(parts)
    
    @staticmethod
    def _process_heading(raw_text: str, seen: Dict[str, int]) -> Tuple[str, str]:
        """Process heading text and generate anchor."""
        text, custom_id = MarkdownProcessor._split_heading(raw_text)
        
        if custom_id:
            return text, custom_id
        
        return text, MarkdownProcessor._unique_slug(text, seen)
    
    @staticmethod
    def _split_heading(text: str) -> Tuple[str, Optional[str]]:
        """Split heading into text and optional custom ID."""
        match = ID_PATTERN.search(text)
        if match:
            return text[:match.start()].strip(), match.group(1)
        return text, None
    
    @staticmethod
    def _unique_slug(text: str, seen: Dict[str, int]) -> str:
        """Generate unique slug for heading."""
        base = MarkdownProcessor._slugify(text)
        if base not in seen:
            seen[base] = 0
            return base
        seen[base] += 1
        return f"{base}-{seen[base]}"
    
    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to URL-safe slug."""
        import unicodedata
        text = unicodedata.normalize("NFKD", text).lower()
        text = re.sub(r"\s+", "-", text)
        text = re.sub(r"[^\w\-]", "", text)
        return text

# ============================================================================
# Chapter Building
# ============================================================================

def create_chapter(name: str, content: str, path: str) -> Dict[str, Any]:
    """Create a chapter structure."""
    return {
        "Chapter": {
            "name": name,
            "content": content,
            "path": path,
            **CHAPTER_TEMPLATE
        }
    }

# ============================================================================
# Content Generators
# ============================================================================

class TitlePageGenerator:
    """Generates title page content."""
    
    @staticmethod
    def generate(config: ConfigManager, version: str, branch: str, status: str) -> str:
        """Generate title page markdown content."""
        title_content = f"""\
<div style="page-break-after: always;">
<div style="text-align:center; margin-top: 120px;">

# {config.title}

<p style="font-size:1.1em; color:#555;">{config.today}</p>

</div>

<div style="margin-top: 80px;">

| | |
|---|---|
| **Author** | {config.author_str} |
| **Version** | {version} |
| **Branch** | {branch} |
| **Status** | {status} |

</div>

<div style="margin-top: 40px;">

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Author | {config.author_str} | | {config.today} |
| Reviewer | {config.reviewer} | | |
| Approver | {config.approver} | | |

</div>
</div>
"""
        return title_content

class HistoryPageGenerator:
    """Generates history page content."""
    
    @staticmethod
    def generate(history_rows: List[Tuple[str, str, str, str, str, str]]) -> str:
        """Generate history page markdown content."""
        lines = ["# 変更履歴\n\n"]
        lines.append('<div class="small">\n\n')
        lines.append("| Date | Commit | Tag | Author | Description | Files |\n")
        lines.append("|------|--------|-----|--------|:------------|:------|\n")
        
        for dt, sha, tag, author, description, files in history_rows:
            lines.append(f"| {dt} | `{sha}` | {tag} | {author} | {description} | {files} |\n")
        
        lines.append('</div>\n\n')
        return "".join(lines)


class ChangelogPageGenerator:
    """Generates detailed changelog page content."""
    
    @staticmethod
    def generate(changelog_entries: List[Tuple[str, str, str, List, str]]) -> str:
        """Generate changelog page markdown content."""
        lines = ["# 詳細変更履歴\n\n"]
        
        for dt, sha, msg, files, description in changelog_entries:
            lines.append(f"## {dt} `{msg.replace(chr(10), '  ')}`\n\n")
            lines.append('<div class="small">\n\n')
            lines.append(f"{sha}: {description}\n\n")
            
            for fstatus, fname, diff in files:
                lines.append(f"**{fstatus}**: `{fname}`\n\n")
                if diff:
                    lines.append(f"~~~diff\n{diff}\n~~~\n\n")
            
            lines.append('</div>\n\n')
        
        return "".join(lines)


class TOCPageGenerator:
    """Generates table of contents page."""
    
    def __init__(self, markdown_processor: MarkdownProcessor):
        self.markdown_processor = markdown_processor
    
    def generate(self, book_items: List[Dict]) -> str:
        """Generate TOC page markdown content."""
        lines = ["# 目次\n\n"]
        
        for item in book_items:
            if not isinstance(item, dict):
                continue
            
            chapter = item.get("Chapter")
            if not chapter:
                continue
            
            name = chapter["name"]
            path = chapter["path"].replace(".md", ".html")
            
            headings = self.markdown_processor.extract_headings(chapter.get("content", ""))
            
            for level, title, anchor in headings:
                indent = "  &nbsp;" * level
                lines.append(f"{indent} [{title}]({path}#{anchor})\n\n")
        
        return "".join(lines)

# ============================================================================
# Main Execution
# ============================================================================

def main():
    """Main entry point for the mdbook preprocessor."""
    context, book = json.load(sys.stdin)
    
    # Initialize components
    config = ConfigManager(context)
    markdown_processor = MarkdownProcessor()
    
    # Get version information
    version, commit, branch, status = GitOperations.get_version_info(config.src_dir)
    
    # Generate title page
    title_content = TitlePageGenerator.generate(config, version, branch, status)
    title_chapter = create_chapter("表紙", title_content, "title.md")
    
    # Generate history page
    history_rows = HistoryExtractor.get_history(config.src_dir)
    history_chapter = None
    if history_rows:
        history_content = HistoryPageGenerator.generate(history_rows)
        history_chapter = create_chapter("変更履歴", history_content, "history.md")
    
    # Generate changelog page
    changelog_entries = ChangelogExtractor.get_changelog(config.src_dir)
    changelog_chapter = None
    if changelog_entries:
        changelog_content = ChangelogPageGenerator.generate(changelog_entries)
        changelog_chapter = create_chapter("詳細変更履歴", changelog_content, "changelog.md")
    
    # Generate TOC page
    toc_generator = TOCPageGenerator(markdown_processor)
    toc_content = toc_generator.generate(book["items"])
    toc_chapter = create_chapter("目次", toc_content, "toc.md")
    
    # Insert chapters in order
    book["items"].insert(0, toc_chapter)
    if history_chapter:
        book["items"].insert(0, history_chapter)
    book["items"].insert(0, title_chapter)
    
    if changelog_chapter:
        book["items"].append(changelog_chapter)
    
    # Output result
    print(json.dumps(book))


if __name__ == "__main__":
    main()
