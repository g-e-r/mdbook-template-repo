# mdbook Template Repository

This repository is a template for creating books using mdbook, with enhanced support for Mermaid diagrams and custom preprocessors.

## Features

- **Mermaid Integration**: Includes `mermaid.min.js` and `mermaid-init.js` for rendering diagrams in the book.
- **Custom Preprocessors**:
  - `mdbook-mermaid-caption.py`: Adds captions to Mermaid diagrams.
  - `mdbook-toc-page.py`: Generates table of contents pages.
- **Custom Theme**: Modified theme files in `theme/` for better styling.
- **Sample Content**: Example documentation in `docs/` including a sample page and diagram.

## Usage

1. Install mdbook: `cargo install mdbook`
2. Clone this repository: `git clone https://github.com/g-e-r/mdbook-template-repo.git`
3. Add your Markdown files to `docs/`
4. Update `SUMMARY.md` to include your chapters.
5. Build the book: `mdbook build`
6. Serve locally: `mdbook serve`

## Building

- HTML: `mdbook build` (outputs to `book/html/`)
- PDF: Use mdbook-pdf or similar plugins, or use the GitHub Action for automated PDF generation.

For more information, see the [mdbook documentation](https://rust-lang.github.io/mdBook/).