#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "beautifulsoup4"  # BeautifulSoup for HTML parsing,
# ]
# ///
import os
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path
import argparse

"""
Script to create a visual HTML diff between two mdBook git revisions.
Uses DaisyDiff for HTML comparison.
"""
from bs4 import BeautifulSoup

DEFAULT_JAR = "daisydiff-1.2-NX5-SNAPSHOT-jar-with-dependencies.jar"

# CSS to highlight DaisyDiff changes within the mdBook theme
DIFF_STYLES = """
<style>
span.diff-html-added {
    background-color: #ccffcc;
    border: 1px solid #99ff99;
}
span.diff-html-removed {
    color: #999999;
    background-color: #ffcccc;
    border: 1px solid #ff9999;
    text-decoration: line-through;
}
span.diff-html-changed {
    background-color: #ffffcc;
    border: 1px solid #ffff99;
}
/* Ensure images and blocks don't break layout when diffed */
.diff-html-added img, .diff-html-changed img { border: 2px solid #28a745; }
.diff-html-removed img { opacity: 0.5; border: 2px solid #dc3545; }
</style>
"""

def run_cmd(cmd, cwd=None):
    print(f"--> Executing: {cmd}")
    subprocess.run(cmd, shell=True, check=True, cwd=cwd)

def build_revision(rev, target_dir):
    """Exports a git revision and builds the mdBook."""
    print(f"[*] Preparing build for revision: {rev}")
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)

    os.makedirs(target_dir, exist_ok=True)

    # Use git clone to preserve history for preprocessors
    tmp_repo = tempfile.mkdtemp()
    try:
        # Clone local repo to preserve history for preprocessors
        run_cmd(f"git clone . {tmp_repo}")
        run_cmd(f"git checkout {rev}", cwd=tmp_repo)

        # Build mdbook
        run_cmd("mdbook build", cwd=tmp_repo)
        build_out = Path(tmp_repo) / "book"
        
        if build_out.exists():
            shutil.copytree(build_out, target_dir, dirs_exist_ok=True)
        else:
            print(f"Error: Build output not found at {build_out}")
            sys.exit(1)
    finally:
        shutil.rmtree(tmp_repo)

def handle_mermaid_blocks(soup):
    """
    Replaces mermaid blocks/figures with simple placeholders to protect them from DaisyDiff.
    Returns a list of the original elements to be restored later.
    """
    saved_elements = []
    for div in soup.find_all(class_='mermaid'):
        # Target the figure if present, otherwise just the div
        target = div.find_parent('figure') or div
        # Use a simple div that DaisyDiff won't mangle
        placeholder = soup.new_tag('div', attrs={'class': 'mermaid-placeholder'})
        target.replace_with(placeholder)
        saved_elements.append(target)
    return saved_elements

def process_html_files(dir_a, dir_b, out_dir, jar_path):
    """Iterates through HTML files and applies DaisyDiff to the content block."""
    path_b = Path(dir_b)
    path_a = Path(dir_a)
    path_out = Path(out_dir)
    
    if path_out.exists():
        shutil.rmtree(path_out)
    shutil.copytree(path_b, path_out)

    for html_file in path_b.rglob("*.html"):
        rel_path = html_file.relative_to(path_b)
        file_a = path_a / rel_path
        file_out = path_out / rel_path

        if not file_a.exists():
            print(f"[-] Skipping {rel_path}: New file (no previous version to diff)")
            continue

        print(f"[+] Diffing {rel_path}...")
        
        with open(file_a, 'r', encoding='utf-8') as f:
            soup_a = BeautifulSoup(f, 'html.parser')
        with open(html_file, 'r', encoding='utf-8') as f:
            soup_b = BeautifulSoup(f, 'html.parser')

        # Protect mermaid blocks from DaisyDiff and ensure they are "ignored" by being identical
        handle_mermaid_blocks(soup_a)
        saved_mermaid_b = handle_mermaid_blocks(soup_b)

        content_a = soup_a.find('div', id='mdbook-content')
        content_b = soup_b.find('div', id='mdbook-content')

        if not content_a or not content_b:
            continue

        # Create temp files for DaisyDiff
        t_a, t_b, t_d = f"{file_out}.a.tmp", f"{file_out}.b.tmp", f"{file_out}.diff.tmp"

        with open(t_a, 'w', encoding='utf-8') as f:
            f.write(f"<html><body>{content_a}</body></html>")
        with open(t_b, 'w', encoding='utf-8') as f:
            f.write(f"<html><body>{content_b}</body></html>")

        try:
            # Run DaisyDiff JAR
            run_cmd(f'java -jar {jar_path} "{t_a}" "{t_b}" --file="{t_d}"')
            
            with open(t_d, 'r', encoding='utf-8') as f:
                diff_soup = BeautifulSoup(f, 'html.parser')

            diff_content = diff_soup.find('body')
            if diff_content:
                with open(file_out, 'r', encoding='utf-8') as f:
                    final_soup = BeautifulSoup(f, 'html.parser')

                target_div = final_soup.find('div', id='mdbook-content')
                if target_div:
                    # Fix the double 'mdbook-content' issue:
                    # DaisyDiff often wraps the result in the same div structure it received.
                    inner_diff = diff_content.find('div', id='mdbook-content')
                    new_content = inner_diff.contents if inner_diff else diff_content.contents
                    target_div.clear()
                    target_div.extend(new_content)

                # Restore Protected Mermaid Blocks
                placeholders = final_soup.find_all(class_='mermaid-placeholder')
                for i, placeholder in enumerate(placeholders):
                    if i < len(saved_mermaid_b):
                        placeholder.replace_with(saved_mermaid_b[i])

                # PDF Cleanup: Remove navigation
                # for selector in ['nav', '#mdbook-sidebar', '#mdbook-menu-bar', '.nav-chapters', '.buttons']:
                #     for match in final_soup.select(selector):
                #         match.decompose()

                # Inject custom CSS to the output head
                if final_soup.head:
                    final_soup.head.append(BeautifulSoup(DIFF_STYLES, 'html.parser'))

                with open(file_out, 'w', encoding='utf-8') as f:
                    f.write(str(final_soup))
        finally:
            for p in [t_a, t_b, t_d]:
                if os.path.exists(p):
                    # os.unlink(p)
                    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create a visual diff between two mdBook revisions.')
    parser.add_argument('rev_a', help='Old git revision (e.g. HEAD~1)')
    parser.add_argument('rev_b', help='New git revision (e.g. HEAD)')
    parser.add_argument('--output', default='book_diff', help='Output directory')
    parser.add_argument('--jar', default=DEFAULT_JAR, help='Path to DaisyDiff JAR')

    args = parser.parse_args()
    
    with tempfile.TemporaryDirectory() as build_root:
        dir_a, dir_b = os.path.join(build_root, "a"), os.path.join(build_root, "b")
        build_revision(args.rev_a, dir_a)
        build_revision(args.rev_b, dir_b)
        process_html_files(dir_a, dir_b, args.output, args.jar)
        print(f"[*] Success! Diff book generated in: {os.path.abspath(args.output)}")