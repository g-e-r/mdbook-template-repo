// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

(() => {
    const darkThemes = ['ayu', 'navy', 'coal'];
    const lightThemes = ['light', 'rust'];

    const classList = document.getElementsByTagName('html')[0].classList;

    let lastThemeWasLight = true;
    for (const cssClass of classList) {
        if (darkThemes.includes(cssClass)) {
            lastThemeWasLight = false;
            break;
        }
    }

    const theme = lastThemeWasLight ? 'default' : 'dark';
    mermaid.initialize({
        startOnLoad: true,
        theme,
        flowchart: {
            padding: 0,
            nodeSpacing: 30,
            rankSpacing: 30
        },
        themeVariables: {
            diagramPadding: 0
        },
        // After all diagrams render, normalize their scale
        deterministicIds: true,
    });

    function normalizeMermaidWidths() {
        const mermaidSvgs = Array.from(document.querySelectorAll('pre.mermaid svg, .mermaid svg'));
        const svgImgs = Array.from(document.querySelectorAll('figure img[src$=".svg"]'));

        // Get natural width of each element
        function naturalWidth(el) {
            if (el.tagName === 'svg' || el.tagName === 'SVG') {
                const vb = el.getAttribute('viewBox');
                if (vb) return parseFloat(vb.split(/\s+/)[2]) || 0;
                return parseFloat(el.getAttribute('width')) || el.getBoundingClientRect().width || 0;
            }
            // img: use naturalWidth if loaded, else current width
            return el.naturalWidth || el.getBoundingClientRect().width || 0;
        }

        const all = [...mermaidSvgs, ...svgImgs];
        if (!all.length) return;

        const widths = all.map(naturalWidth);
        const maxNatural = Math.max(...widths);
        if (!maxNatural) return;

        const containerW = (document.querySelector('.content') || document.body).clientWidth * 0.9;
        const scale = Math.min(1, containerW / maxNatural);
        console.log(`Scaling mermaid diagrams by ${scale.toFixed(2)} to fit container`);

        all.forEach((el, i) => {
            el.style.width = (widths[i] * scale) + 'px';
            el.style.height = 'auto';
        });
    }

    // mermaid 10.x fires this event when all diagrams are rendered
    document.addEventListener('mermaid.init', normalizeMermaidWidths);
    // Fallback: poll until SVGs appear and img elements are loaded
    let attempts = 0;
    const poll = setInterval(() => {
        const svgs = document.querySelectorAll('pre.mermaid svg');
        const imgs = document.querySelectorAll('figure img[src$=".svg"]');
        const imgsLoaded = Array.from(imgs).every(img => img.complete && img.naturalWidth > 0);
        if ((svgs.length && imgsLoaded) || ++attempts > 20) {
            clearInterval(poll);
            normalizeMermaidWidths();
        }
    }, 200);

    // Simplest way to make mermaid re-render the diagrams in the new theme is via refreshing the page

    for (const darkTheme of darkThemes) {
        document.getElementById(darkTheme).addEventListener('click', () => {
            if (lastThemeWasLight) {
                window.location.reload();
            }
        });
    }

    for (const lightTheme of lightThemes) {
        document.getElementById(lightTheme).addEventListener('click', () => {
            if (!lastThemeWasLight) {
                window.location.reload();
            }
        });
    }
})();
