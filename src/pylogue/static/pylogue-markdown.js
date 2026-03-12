import { marked } from "https://cdn.jsdelivr.net/npm/marked/lib/marked.esm.js";
marked.setOptions({ gfm: true, breaks: true });

let markdownRendering = false;
let pendingScrollState = null;
const KATEX_DOLLAR_PLACEHOLDER = "@@PYLOGUE_DOLLAR@@";

const getScrollState = () => {
    const scrollElement = document.scrollingElement || document.documentElement;
    if (!scrollElement) return null;
    const maxScrollTop =
        scrollElement.scrollHeight - scrollElement.clientHeight;
    const atBottom = maxScrollTop - scrollElement.scrollTop < 24;
    return { top: scrollElement.scrollTop, atBottom };
};

const restoreScrollState = (state) => {
    if (!state) return;
    const scrollElement = document.scrollingElement || document.documentElement;
    if (!scrollElement) return;
    if (state.atBottom) {
        scrollElement.scrollTop = scrollElement.scrollHeight;
    } else {
        scrollElement.scrollTop = state.top;
    }
};

const forceScrollToBottom = () => {
    const scrollElement = document.scrollingElement || document.documentElement;
    if (!scrollElement) return;
    const anchor = document.getElementById("scroll-anchor");
    const apply = () => {
        if (anchor) {
            anchor.scrollIntoView({ block: "end" });
        } else {
            scrollElement.scrollTop = scrollElement.scrollHeight;
        }
    };
    requestAnimationFrame(() => {
        apply();
        setTimeout(apply, 0);
        setTimeout(apply, 50);
        setTimeout(apply, 150);
    });
};
window.__forceScrollToBottom = forceScrollToBottom;

const isNearBottom = (threshold = 32) => {
    const scrollElement = document.scrollingElement || document.documentElement;
    if (!scrollElement) return false;
    const maxScrollTop =
        scrollElement.scrollHeight - scrollElement.clientHeight;
    return maxScrollTop - scrollElement.scrollTop <= threshold;
};

let bottomLockUntil = 0;
let bottomLockRaf = null;

const tickBottomLock = () => {
    const now = Date.now();
    if (now > bottomLockUntil) {
        bottomLockRaf = null;
        return;
    }
    const scrollElement = document.scrollingElement || document.documentElement;
    if (scrollElement) {
        scrollElement.scrollTop = scrollElement.scrollHeight;
    }
    bottomLockRaf = requestAnimationFrame(tickBottomLock);
};

const startBottomLock = (durationMs = 1200) => {
    if (!isNearBottom()) return;
    bottomLockUntil = Date.now() + durationMs;
    if (!bottomLockRaf) {
        bottomLockRaf = requestAnimationFrame(tickBottomLock);
    }
};

const decodeB64 = (value) => {
    if (!value) return "";
    try {
        const binary = atob(value);
        const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
        const decoded = new TextDecoder("utf-8").decode(bytes);
        return decoded;
    } catch (error) {
        return "";
    }
};

const protectEscapedDollars = (md) => {
    if (!md) return md || "";
    const blocks = [];
    const replaceBlock = (match) => {
        blocks.push(match);
        return `__PYLOGUE_CODEBLOCK_${blocks.length - 1}__`;
    };
    md = md.replace(/(```+|~~~+)[\s\S]*?\1/g, replaceBlock);
    md = md.replace(/(`+)([^`]*?)\1/g, replaceBlock);
    md = md.replace(/(\\+)\$/g, (match, slashes) => {
        return "\\".repeat(slashes.length - 1) + KATEX_DOLLAR_PLACEHOLDER;
    });
    blocks.forEach((block, index) => {
        md = md.replace(`__PYLOGUE_CODEBLOCK_${index}__`, block);
    });
    return md;
};

const looksLikeHtmlBlock = (text) => {
    if (!text) return false;
    const trimmed = text.trim();
    if (!trimmed.startsWith("<") || !trimmed.endsWith(">")) return false;
    return /<\/?[a-zA-Z][\s\S]*?>/.test(trimmed);
};

const containsHtmlAndMarkdown = (text) => {
    if (!text) return false;
    
    // Check for HTML elements or Pylogue HTML placeholders
    const hasHtml = /<\/?[a-zA-Z][\s\S]*?>/.test(text);
    const hasPylogueHtml = /\{_pylogue_html_id:\s*"[^"]+"\}/.test(text);
    
    if (!hasHtml && !hasPylogueHtml) return false;
    
    // Check for markdown patterns (tables, headers, emphasis, etc.)
    const markdownPatterns = [
        /\|.*\|.*\|/,           // Table rows
        /^#+\s/m,              // Headers
        /\*\*.*\*\*/,          // Bold
        /^\s*\*\s+/m,          // Lists with asterisks
        /^-\s/m,               // Lists with dashes
        /^\d+\.\s/m,          // Numbered lists
        /```[\s\S]*?```/,      // Code blocks
    ];
    
    const matchedPatterns = markdownPatterns.filter(pattern => pattern.test(text));
    const hasMixed = matchedPatterns.length > 0;
    return hasMixed;
};

const processMixedContent = (content) => {
    if (!content) return content;
    
    // First, identify and protect tool status blocks as complete units
    const toolStatusBlocks = [];
    let protectedContent = content;
    
    // Match complete tool status structures (including nested elements)
    const toolStatusRegex = /<div[^>]*class="tool-status-update"[^>]*>[\s\S]*?<\/div>\s*(?:<span[^>]*class="tool-status-check"[^>]*>[\s\S]*?<\/span>)?/g;
    let toolMatch;
    let toolIndex = 0;
    
    while ((toolMatch = toolStatusRegex.exec(content)) !== null) {
        const placeholder = `__PYLOGUE_TOOL_STATUS_${toolIndex}__`;
        toolStatusBlocks.push(toolMatch[0]);
        protectedContent = protectedContent.replace(toolMatch[0], placeholder);
        toolIndex++;
    }
    
    // Also protect Pylogue HTML placeholders
    const pylogueHtmlBlocks = [];
    const pylogueHtmlRegex = /\{_pylogue_html_id:\s*"[^"]+"\}/g;
    let pylogueMatch;
    let pylogueIndex = 0;
    
    while ((pylogueMatch = pylogueHtmlRegex.exec(protectedContent)) !== null) {
        const placeholder = `__PYLOGUE_HTML_PLACEHOLDER_${pylogueIndex}__`;
        pylogueHtmlBlocks.push(pylogueMatch[0]);
        protectedContent = protectedContent.replace(pylogueMatch[0], placeholder);
        pylogueIndex++;
    }
    
    // Now split the protected content into segments: HTML elements and non-HTML text
    const segments = [];
    let currentPos = 0;
    
    // Find HTML blocks - improved regex to handle nested and complex structures
    const htmlBlocks = [];
    
    // First, find all HTML opening tags
    const tagRegex = /<([a-zA-Z][^>\/]*)(?:[^>]*)>/g;
    let tagMatch;
    
    while ((tagMatch = tagRegex.exec(protectedContent)) !== null) {
        const tagName = tagMatch[1].split(/\s/)[0]; // Get just the tag name
        const tagStart = tagMatch.index;
        // Find the matching closing tag
        let depth = 1;
        let searchPos = tagMatch.index + tagMatch[0].length;
        const openTagRegex = new RegExp(`<${tagName}(?:\\s[^>]*)?>`, 'gi');
        const closeTagRegex = new RegExp(`<\/${tagName}>`, 'gi');
        
        while (depth > 0 && searchPos < protectedContent.length) {
            openTagRegex.lastIndex = searchPos;
            closeTagRegex.lastIndex = searchPos;
            
            const nextOpen = openTagRegex.exec(protectedContent);
            const nextClose = closeTagRegex.exec(protectedContent);
            
            if (nextClose && (!nextOpen || nextClose.index < nextOpen.index)) {
                depth--;
                searchPos = nextClose.index + nextClose[0].length;
            } else if (nextOpen) {
                depth++;
                searchPos = nextOpen.index + nextOpen[0].length;
            } else {
                break;
            }
        }
        
        if (depth === 0) {
            htmlBlocks.push({
                start: tagStart,
                end: searchPos,
                content: protectedContent.slice(tagStart, searchPos)
            });
        }
    }
    
    // Sort HTML blocks by start position and merge overlapping ones
    htmlBlocks.sort((a, b) => a.start - b.start);
    const mergedBlocks = [];
    for (const block of htmlBlocks) {
        const lastBlock = mergedBlocks[mergedBlocks.length - 1];
        if (lastBlock && block.start <= lastBlock.end) {
            // Extend the last block if they overlap
            lastBlock.end = Math.max(lastBlock.end, block.end);
            lastBlock.content = protectedContent.slice(lastBlock.start, lastBlock.end);
        } else {
            mergedBlocks.push(block);
        }
    }
    
    // Create segments from merged blocks
    let pos = 0;
    for (const htmlBlock of mergedBlocks) {
        // Add text before HTML block as markdown
        if (htmlBlock.start > pos) {
            const textContent = protectedContent.slice(pos, htmlBlock.start).trim();
            if (textContent) {
                segments.push({
                    type: 'markdown',
                    content: textContent
                });
            }
        }
        
        // Add HTML block
        segments.push({
            type: 'html',
            content: htmlBlock.content.trim()
        });
        
        pos = htmlBlock.end;
    }
    
    // Add any remaining text after last HTML block
    if (pos < protectedContent.length) {
        const remainingText = protectedContent.slice(pos).trim();
        if (remainingText) {
            segments.push({
                type: 'markdown',
                content: remainingText
            });
        }
    }
    
    // Process each segment and combine
    const processedSegments = segments.map((segment, index) => {
        if (segment.type === 'html') {
            return segment.content;
        } else {
            // Process markdown, but protect our placeholders from being altered
            try {
                let segmentContent = segment.content;
                
                // Temporarily protect any remaining placeholders in markdown content
                const placeholderMatches = segmentContent.match(/__PYLOGUE_(TOOL_STATUS|HTML_PLACEHOLDER)_\d+__/g) || [];
                const tempProtections = {};
                
                placeholderMatches.forEach((placeholder, i) => {
                    const tempKey = `__TEMP_PROTECT_${i}__`;
                    tempProtections[tempKey] = placeholder;
                    segmentContent = segmentContent.replace(placeholder, tempKey);
                });
                
                const processed = marked.parse(segmentContent);
                
                // Restore protected placeholders
                let finalProcessed = processed;
                Object.keys(tempProtections).forEach(tempKey => {
                    finalProcessed = finalProcessed.replace(tempKey, tempProtections[tempKey]);
                });
                

                return finalProcessed;
            } catch (error) {
                return segment.content;
            }
        }
    });
    
    let result = processedSegments.join('\n');
    
    // Restore protected tool status blocks
    toolStatusBlocks.forEach((block, index) => {
        const placeholder = `__PYLOGUE_TOOL_STATUS_${index}__`;
        result = result.replace(placeholder, block);
    });
    
    // Restore protected Pylogue HTML placeholders
    pylogueHtmlBlocks.forEach((block, index) => {
        const placeholder = `__PYLOGUE_HTML_PLACEHOLDER_${index}__`;
        result = result.replace(placeholder, block);
    });
    
    // Final cleanup: remove any remaining placeholders that shouldn't be visible
    const remainingPlaceholders = result.match(/__PYLOGUE_(TOOL_STATUS|HTML_PLACEHOLDER)_\d+__/g);
    if (remainingPlaceholders && remainingPlaceholders.length > 0) {
        // Remove them to prevent showing in UI
        remainingPlaceholders.forEach(placeholder => {
            result = result.replace(new RegExp(placeholder, 'g'), '');
        });
    }

    
    return result;
};

const dedentHtml = (text) => {
    if (!looksLikeHtmlBlock(text)) return text;
    const lines = text.split(/\r?\n/);
    let minIndent = null;
    lines.forEach((line) => {
        if (!line.trim()) return;
        const match = line.match(/^[ \t]+/);
        if (!match) {
            minIndent = 0;
            return;
        }
        const indent = match[0].length;
        if (minIndent === null || indent < minIndent) {
            minIndent = indent;
        }
    });
    if (!minIndent) return text;
    const strip = new RegExp(`^[ \\t]{0,${minIndent}}`);
    return lines.map((line) => line.replace(strip, "")).join("\n");
};

const splitDivHtmlBlock = (text) => {
    if (!text) return null;
    if (text.includes("```")) return null;
    const start = text.indexOf("<div");
    const end = text.lastIndexOf("</div>");
    if (start === -1 || end === -1 || end <= start) return null;
    const htmlEnd = end + 6;
    return {
        prefix: text.slice(0, start),
        html: text.slice(start, htmlEnd),
        suffix: text.slice(htmlEnd),
    };
};

const replaceDollarPlaceholders = (root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let node;
    while ((node = walker.nextNode())) {
        if (
            node.nodeValue &&
            node.nodeValue.includes(KATEX_DOLLAR_PLACEHOLDER)
        ) {
            nodes.push(node);
        }
    }
    nodes.forEach((textNode) => {
        textNode.nodeValue = textNode.nodeValue
            .split(KATEX_DOLLAR_PLACEHOLDER)
            .join("$");
    });
};

const renderMath = (root) => {
    if (typeof renderMathInElement !== "function") return;
    renderMathInElement(root, {
        delimiters: [
            { left: "$$", right: "$$", display: true },
            { left: "$", right: "$", display: false },
        ],
        throwOnError: false,
        ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"],
    });
    replaceDollarPlaceholders(root);
};

const highlightCode = (root) => {
    if (!window.hljs || typeof window.hljs.highlightElement !== "function")
        return;
    const blocks = root.querySelectorAll("pre code");
    blocks.forEach((block) => {
        if (block.dataset.hljsApplied === "true") return;
        window.hljs.highlightElement(block);
        block.dataset.hljsApplied = "true";
    });
};

const addCopyButtons = (root) => {
    const blocks = root.querySelectorAll("pre");
    blocks.forEach((pre) => {
        if (pre.dataset.copyBound === "true") return;
        const code = pre.querySelector("code");
        if (!code) return;
        pre.dataset.copyBound = "true";
        pre.classList.add("codeblock");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "code-copy-btn";
        btn.setAttribute("aria-label", "Copy code");
        btn.setAttribute("title", "Copy code");
        btn.innerHTML = `
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                <rect x="9" y="9" width="10" height="10" rx="2"></rect>
                                <rect x="5" y="5" width="10" height="10" rx="2"></rect>
                            </svg>
                        `;
        btn.addEventListener("click", async (event) => {
            event.preventDefault();
            const text = code.innerText || code.textContent || "";
            try {
                await navigator.clipboard.writeText(text);
                btn.dataset.copied = "true";
                setTimeout(() => {
                    btn.dataset.copied = "false";
                }, 1200);
            } catch {
                const textarea = document.createElement("textarea");
                textarea.value = text;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
                btn.dataset.copied = "true";
                setTimeout(() => {
                    btn.dataset.copied = "false";
                }, 1200);
            }
        });
        pre.appendChild(btn);
    });
};

const renderMarkdown = (root = document) => {
    const nodes = root.querySelectorAll(".marked");
    
    if (!marked || typeof marked.parse !== "function") {
        return;
    }
    if (nodes.length === 0) {
        return;
    }
    
    markdownRendering = true;
    nodes.forEach((el, index) => {
        const rawB64 = el.getAttribute("data-raw-b64");
        const rawAttr = el.getAttribute("data-raw");
        const source = rawB64
            ? decodeB64(rawB64)
            : rawAttr !== null
              ? rawAttr
              : el.textContent;
        
        if (!source) {
            return;
        }
              
        // Early exit if already rendered with exact same source
        if (el.dataset.renderedSource === source) {
            return;
        }
        
        // Early exit if element is locked (contains graphs/scripts that shouldn't be re-rendered)
        if (el.dataset.htmlLocked === "true") {
            el.dataset.renderedSource = source;
            return;
        }
        
        if (el.dataset.mermaidDirty === "true") {
            return;
        }
        
        const normalizedSource = dedentHtml(source);
        
        // Check if we have mixed content FIRST - bypass splitDivHtmlBlock for proper text formatting
        const isMixed = containsHtmlAndMarkdown(normalizedSource);

        const split = splitDivHtmlBlock(normalizedSource);
        if (split && !isMixed) {
            const safePrefix = protectEscapedDollars(split.prefix);
            const safeSuffix = protectEscapedDollars(split.suffix);
            const prefixHtml = safePrefix ? marked.parse(safePrefix) : "";
            const suffixHtml = safeSuffix ? marked.parse(safeSuffix) : "";
            el.innerHTML = `${prefixHtml}${split.html}${suffixHtml}`;
            renderMath(el);
            highlightCode(el);
            addCopyButtons(el);
            el.dataset.renderedSource = source;
            return;
        }
        
        const isHtml = looksLikeHtmlBlock(normalizedSource);
        
        // Check for mixed HTML/Markdown content FIRST (before pure HTML check)
        if (isMixed) {
            const processedContent = processMixedContent(normalizedSource);
            el.innerHTML = processedContent;
            el.dataset.renderedSource = source;
            renderMath(el);
            highlightCode(el);
            addCopyButtons(el);
            
            requestAnimationFrame(() => {
                if (window.__applyToolStatusUpdates) {
                    window.__applyToolStatusUpdates(document);
                }
            });
        } else if (isHtml) {
            if (el.dataset.htmlLocked === "true") return;
            if (el.dataset.renderedSource === source) return;
            
            if (el.querySelector('iframe') && el.dataset.renderedSource) {
                el.dataset.htmlLocked = "true";
                el.dataset.renderedSource = source;
                return;
            }
            
            const currentContent = el.innerHTML.trim();
            const newContent = normalizedSource.trim();
            if (currentContent === newContent && el.dataset.renderedSource) {
                el.dataset.renderedSource = source;
                el.dataset.htmlLocked = "true";
                return;
            }
            el.innerHTML = normalizedSource;
            el.dataset.renderedSource = source;
            
            // If this HTML contains script tags (like Plotly) or iframes, lock it immediately
            if (normalizedSource.includes('<script') || normalizedSource.includes('plotly') || normalizedSource.includes('<iframe')) {
                el.dataset.htmlLocked = "true";
            }
            
            // Scroll after HTML content (like charts) is rendered
            requestAnimationFrame(() => {
                if (window.__applyToolStatusUpdates) {
                    window.__applyToolStatusUpdates(document);
                }
                if (window.__forceScrollToBottom) {
                    window.__forceScrollToBottom();
                }
            });
            // Also apply status updates with a slight delay to catch late arrivals
            setTimeout(() => {
                if (window.__applyToolStatusUpdates) {
                    window.__applyToolStatusUpdates(document);
                }
            }, 100);
        } else {
            // Handle pure markdown content            
            const safeSource = protectEscapedDollars(normalizedSource);
            const parsedMarkdown = marked.parse(safeSource);
            

            
            el.innerHTML = parsedMarkdown;
            renderMath(el);
            highlightCode(el);
            addCopyButtons(el);
            el.dataset.renderedSource = source;
        }
    });
    markdownRendering = false;
    if (window.__upgradeMermaidBlocks) {
        window.__upgradeMermaidBlocks(root);
    }
    if (window.__applyToolStatusUpdates) {
        window.__applyToolStatusUpdates(root);
        // Call again with delay to catch late-arriving status updates
        setTimeout(() => {
            if (window.__applyToolStatusUpdates) {
                window.__applyToolStatusUpdates(document);
            }
        }, 50);
    }
};

const observeMarkdown = () => {
    const target = document.body;
    if (!target) {
        return;
    }
    
    let renderTimer = null;
    const scheduleRender = () => {
        if (markdownRendering) return;
        if (renderTimer) return;
        renderTimer = requestAnimationFrame(() => {
            renderTimer = null;
            renderMarkdown(document);
        });
    };
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type !== "characterData") continue;
            const parent = mutation.target && mutation.target.parentElement;
            if (!parent) continue;
            const markedRoot = parent.closest(".marked");
            if (!markedRoot) continue;
            const rawText = markedRoot.getAttribute("data-raw") || "";
            if (!isMermaidFenceClosed(rawText)) {
                markedRoot.dataset.mermaidDirty = "true";
            } else if (markedRoot.dataset.mermaidDirty === "true") {
                markedRoot.dataset.mermaidDirty = "false";
            }
        }
        scheduleRender();
    });
    observer.observe(target, {
        childList: true,
        subtree: true,
        characterData: true,
    });
    renderMarkdown(document);
};

const applyToolStatusUpdates = (root = document) => {
    const updates = root.querySelectorAll(
        ".tool-status-update[data-target-id]",
    );
    updates.forEach((update) => {
        const targetId = update.getAttribute("data-target-id");
        if (!targetId) return;
        const status = (update.getAttribute("data-status") || "done")
            .toLowerCase()
            .trim();
        const statusClass =
            status === "running" ? "tool-status--running" : "tool-status--done";
        const existing = Array.from(
            document.querySelectorAll(`[id="${targetId}"]`),
        );
        const target = existing.length ? existing[existing.length - 1] : null;
        const replacement = document.createElement("div");
        replacement.id = targetId;
        replacement.className = `tool-status ${statusClass}`;
        replacement.innerHTML = update.innerHTML || "Completed";
        if (target) {
            target.replaceWith(replacement);
            update.remove();
            existing.slice(0, -1).forEach((node) => node.remove());
        } else {
            update.replaceWith(replacement);
        }
    });
};
window.__applyToolStatusUpdates = applyToolStatusUpdates;

// Store iframes before htmx swaps to prevent reloading graphs
let preservedIframes = [];

document.body.addEventListener("htmx:beforeSwap", (event) => {
    const target = event.detail && event.detail.target;
    if (target && target.id === "cards") {
        // Find all iframes with graphs and preserve them BY REFERENCE
        const markedElements = target.querySelectorAll('.marked');
        preservedIframes = [];
        
        markedElements.forEach((markedElement, index) => {
            const iframe = markedElement.querySelector('iframe');
            if (iframe) {
                // Extract a unique identifier from the parent's data-raw-b64 or content
                const rawB64 = markedElement.getAttribute('data-raw-b64');
                const rawAttr = markedElement.getAttribute('data-raw');
                const contentHash = rawB64 || rawAttr || markedElement.textContent.substring(0, 100);
                
                preservedIframes.push({
                    iframe: iframe,  // Actual DOM element reference
                    contentHash: contentHash,
                    index: index
                });

            }
        });
    }
});

document.addEventListener("DOMContentLoaded", () => {
    // Check for .marked elements immediately
    const markedElements = document.querySelectorAll('.marked');
    
    markedElements.forEach((el, index) => {
        // Element info logging removed
    });
    
    observeMarkdown();
    renderMarkdown(document);
});

document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail && event.detail.target;
    
    // Restore preserved iframes after swap to prevent reloading
    if (target && target.id === "cards" && preservedIframes.length > 0) {
        const newMarkedElements = target.querySelectorAll('.marked');
        
        newMarkedElements.forEach((markedElement, index) => {
            const rawB64 = markedElement.getAttribute('data-raw-b64');
            const rawAttr = markedElement.getAttribute('data-raw');
            const contentHash = rawB64 || rawAttr || markedElement.textContent.substring(0, 100);
            
            // Find matching preserved iframe by content hash
            const preserved = preservedIframes.find(p => 
                p.contentHash === contentHash || p.index === index
            );
            
            if (preserved && preserved.iframe) {
                const existingIframe = markedElement.querySelector('iframe');
                
                // Only restore if new DOM doesn't already have an iframe
                if (!existingIframe) {
                    // Clear the marked element and insert the preserved iframe
                    markedElement.innerHTML = '';
                    markedElement.appendChild(preserved.iframe);
                    markedElement.dataset.htmlLocked = "true";
                    markedElement.dataset.renderedSource = "locked";
                }
            }
        });
        
        // Clear after restoration
        setTimeout(() => {
            preservedIframes = [];
        }, 100);
    }
    
    renderMarkdown(event.target || document);
});

document.body.addEventListener("htmx:beforeSwap", (event) => {
    const target = event.detail && event.detail.target;
    const cardsRoot =
        target && (target.closest ? target.closest("#cards") : null);
    if (cardsRoot) {
        pendingScrollState = getScrollState();
    }
});

document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail && event.detail.target;
    const cardsRoot =
        target && (target.closest ? target.closest("#cards") : null);
    if (cardsRoot) {
        const state = pendingScrollState;
        pendingScrollState = null;
        if (state && state.atBottom) {
            restoreScrollState(state);
        } else {
            forceScrollToBottom();
        }
    }
});

document.body.addEventListener("htmx:wsAfterMessage", () => {
    startBottomLock();
});

document.body.addEventListener("htmx:wsBeforeMessage", () => {
    startBottomLock();
});

document.addEventListener(
    "scroll",
    () => {
        if (!isNearBottom()) {
            bottomLockUntil = 0;
            bottomLockRaf = null;
        }
    },
    { passive: true },
);

import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";

let mermaidReady = false;
let mermaidCounter = 0;
const mermaidStates = {};
const mermaidCache = new Map();
const mermaidRenderPromises = new Map();

const ensureMermaid = () => {
    if (mermaidReady) return;
    mermaid.initialize({
        startOnLoad: false,
        suppressErrorRendering: true,
        theme: "dark",
        themeVariables: {
            // Ensure dark text on all node backgrounds for readability
            primaryColor: "#4A90E2",
            primaryTextColor: "#000000",
            primaryBorderColor: "#2E5C8A",
            lineColor: "#6C757D",
            secondaryColor: "#7ED321",
            secondaryTextColor: "#000000",
            secondaryBorderColor: "#5FA319",
            tertiaryColor: "#FF6B6B",
            tertiaryTextColor: "#000000",
            tertiaryBorderColor: "#CC5555",
            noteBkgColor: "#FFA500",
            noteTextColor: "#000000",
            noteBorderColor: "#CC8400",
            // Additional colors for flowcharts
            nodeBorder: "#333333",
            mainBkg: "#5DADE2",
            textColor: "#000000",
        },
    });
    mermaidReady = true;
};

const hashMermaidCode = (text) => {
    let hash = 0;
    for (let i = 0; i < text.length; i += 1) {
        hash = (hash << 5) - hash + text.charCodeAt(i);
        hash |= 0;
    }
    return `m${Math.abs(hash)}`;
};

const applyMermaidState = (wrapper, state) => {
    const svg = wrapper.querySelector("svg");
    if (!svg) return;
    svg.style.pointerEvents = "none";
    svg.style.transform = `translate(${state.translateX}px, ${state.translateY}px) scale(${state.scale})`;
    svg.style.transformOrigin = "center center";
};

const fitSvgToWrapper = (wrapper, state) => {
    const svg = wrapper.querySelector("svg");
    if (!svg) return;
    const wrapperRect = wrapper.getBoundingClientRect();
    const svgRect = svg.getBoundingClientRect();
    if (
        !wrapperRect.width ||
        !wrapperRect.height ||
        !svgRect.width ||
        !svgRect.height
    )
        return;
    const padding = 16;
    const scaleX = (wrapperRect.width - padding) / svgRect.width;
    const scaleY = (wrapperRect.height - padding) / svgRect.height;
    const initialScale = Math.min(scaleX, scaleY, 1);
    state.scale = initialScale;
    state.translateX = 0;
    state.translateY = 0;
    applyMermaidState(wrapper, state);
};

const initMermaidInteraction = (wrapper) => {
    if (wrapper.dataset.mermaidInteractive === "true") return;
    const svg = wrapper.querySelector("svg");
    if (!svg) return;

    const state = {
        scale: 1,
        translateX: 0,
        translateY: 0,
        isPanning: false,
        startX: 0,
        startY: 0,
    };
    mermaidStates[wrapper.id] = state;
    wrapper.dataset.mermaidInteractive = "true";

    fitSvgToWrapper(wrapper, state);

    wrapper.style.cursor = "grab";
    wrapper.style.touchAction = "none";

    wrapper.addEventListener(
        "wheel",
        (e) => {
            e.preventDefault();
            const currentSvg = wrapper.querySelector("svg");
            if (!currentSvg) return;
            const rect = currentSvg.getBoundingClientRect();
            const mouseX = e.clientX - rect.left - rect.width / 2;
            const mouseY = e.clientY - rect.top - rect.height / 2;
            const zoomIntensity = 0.01;
            const delta = e.deltaY > 0 ? 1 - zoomIntensity : 1 + zoomIntensity;
            const newScale = Math.min(Math.max(0.1, state.scale * delta), 12);
            const scaleFactor = newScale / state.scale - 1;
            state.translateX -= mouseX * scaleFactor;
            state.translateY -= mouseY * scaleFactor;
            state.scale = newScale;
            applyMermaidState(wrapper, state);
        },
        { passive: false },
    );

    wrapper.addEventListener("pointerdown", (e) => {
        if (e.pointerType === "mouse" && e.button !== 0) return;
        state.isPanning = true;
        state.startX = e.clientX - state.translateX;
        state.startY = e.clientY - state.translateY;
        wrapper.setPointerCapture(e.pointerId);
        wrapper.style.cursor = "grabbing";
        e.preventDefault();
    });

    wrapper.addEventListener("pointermove", (e) => {
        if (!state.isPanning) return;
        state.translateX = e.clientX - state.startX;
        state.translateY = e.clientY - state.startY;
        applyMermaidState(wrapper, state);
    });

    const stopPanning = (e) => {
        if (!state.isPanning) return;
        state.isPanning = false;
        try {
            wrapper.releasePointerCapture(e.pointerId);
        } catch {
            // Ignore if pointer capture is not active
        }
        wrapper.style.cursor = "grab";
    };
    wrapper.addEventListener("pointerup", stopPanning);
    wrapper.addEventListener("pointercancel", stopPanning);
};

const scheduleMermaidInteraction = (
    wrapper,
    { maxAttempts = 12, delayMs = 80 } = {},
) => {
    let attempt = 0;
    const check = () => {
        if (wrapper.querySelector("svg")) {
            initMermaidInteraction(wrapper);
            return;
        }
        if (attempt >= maxAttempts) return;
        attempt += 1;
        setTimeout(check, delayMs);
    };
    check();
};

const ensureMermaidInteractions = (root = document) => {
    const wrappers = root.querySelectorAll(".mermaid-wrapper");
    wrappers.forEach((wrapper) => {
        if (wrapper.dataset.mermaidInteractive === "true") return;
        if (wrapper.querySelector("svg")) {
            initMermaidInteraction(wrapper);
        } else {
            scheduleMermaidInteraction(wrapper);
        }
    });
};

const createMermaidContainer = (codeText) => {
    mermaidCounter += 1;
    const diagramId = `chat-mermaid-${mermaidCounter}`;
    const codeKey = String(codeText || "").slice(0, 120);

    const container = document.createElement("div");
    container.className = "mermaid-container";

    const controls = document.createElement("div");
    controls.className = "mermaid-controls";
    controls.innerHTML = `
                        <button type="button" data-action="reset" title="Reset zoom">Reset</button>
                        <button type="button" data-action="zoom-in" title="Zoom in">+</button>
                        <button type="button" data-action="zoom-out" title="Zoom out">−</button>
                    `;

    const wrapper = document.createElement("div");
    wrapper.id = diagramId;
    wrapper.className = "mermaid-wrapper";
    wrapper.dataset.mermaidCode = codeText;
    wrapper.dataset.mermaidRendered = "false";

    const pre = document.createElement("pre");
    pre.className = "mermaid";
    pre.textContent = codeText;
    wrapper.appendChild(pre);

    container.appendChild(controls);
    container.appendChild(wrapper);

    controls.addEventListener("click", (event) => {
        const btn = event.target.closest("button");
        if (!btn) return;
        const action = btn.getAttribute("data-action");
        if (action === "reset") {
            resetMermaidZoom(wrapper.id);
        } else if (action === "zoom-in") {
            zoomMermaidIn(wrapper.id);
        } else if (action === "zoom-out") {
            zoomMermaidOut(wrapper.id);
        }
    });

    return { container, wrapper };
};

const renderMermaidWrapper = async (wrapper) => {
    if (!wrapper || wrapper.dataset.mermaidRendering === "true") return;
    const codeText = wrapper.dataset.mermaidCode || "";
    if (!codeText.trim()) return;
    const cacheHit = mermaidCache.get(codeText);
    if (cacheHit) {
        wrapper.innerHTML = cacheHit;
        wrapper.dataset.mermaidRendered = "true";
        wrapper.dataset.mermaidRendering = "false";
        scheduleMermaidInteraction(wrapper);
        return;
    }
    const renderId = `${hashMermaidCode(codeText)}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    wrapper.dataset.mermaidRendering = "true";
    ensureMermaid();
    let promise = mermaidRenderPromises.get(codeText);
    if (!promise) {
        promise = mermaid.render(renderId, codeText);
        mermaidRenderPromises.set(codeText, promise);
    }
    try {
        const result = await promise;
        const svg = result && result.svg ? result.svg : "";
        if (!svg) {
            throw new Error("Mermaid render returned empty svg");
        }
        wrapper.innerHTML = svg;
        if (result && typeof result.bindFunctions === "function") {
            result.bindFunctions(wrapper);
        }
        mermaidCache.set(codeText, svg);
        wrapper.dataset.mermaidRendered = "true";
        wrapper.dataset.mermaidError = "false";
        scheduleMermaidInteraction(wrapper);
    } catch (err) {
        wrapper.innerHTML =
            '<div class="mermaid-error">Invalid Mermaid diagram</div>';

    } finally {
        wrapper.dataset.mermaidRendering = "false";
        mermaidRenderPromises.delete(codeText);
    }
};

const resetMermaidZoom = (id) => {
    const state = mermaidStates[id];
    const wrapper = document.getElementById(id);
    if (!state || !wrapper) return;
    fitSvgToWrapper(wrapper, state);
};

const zoomMermaidIn = (id) => {
    const state = mermaidStates[id];
    const wrapper = document.getElementById(id);
    if (!state || !wrapper) return;
    state.scale = Math.min(state.scale * 1.1, 12);
    applyMermaidState(wrapper, state);
};

const zoomMermaidOut = (id) => {
    const state = mermaidStates[id];
    const wrapper = document.getElementById(id);
    if (!state || !wrapper) return;
    state.scale = Math.max(state.scale * 0.9, 0.1);
    applyMermaidState(wrapper, state);
};

const isMermaidFenceClosed = (rawText) => {
    if (!rawText) return true;
    const openIndex = rawText.lastIndexOf("```mermaid");
    if (openIndex === -1) return true;
    const closeIndex = rawText.indexOf("```", openIndex + 3);
    return closeIndex !== -1;
};

let mermaidRenderTimer = null;

const upgradeMermaidBlocks = (root = document) => {
    const blocks = root.querySelectorAll("pre > code.language-mermaid");
    const wrappers = [];
    blocks.forEach((code) => {
        if (code.dataset.mermaidProcessed === "true") return;
        const markedRoot = code.closest(".marked");
        const rawSource = markedRoot
            ? markedRoot.getAttribute("data-raw")
            : null;
        if (rawSource && !isMermaidFenceClosed(rawSource)) {
            return;
        }
        code.dataset.mermaidProcessed = "true";
        const pre = code.parentElement;
        if (!pre) return;
        const codeText = code.textContent || "";
        const { container, wrapper } = createMermaidContainer(codeText);
        pre.replaceWith(container);
        const cachedSvg = mermaidCache.get(codeText);
        if (cachedSvg) {
            wrapper.innerHTML = cachedSvg;
            wrapper.dataset.mermaidRendered = "true";
            scheduleMermaidInteraction(wrapper);
            return;
        }
        if (
            wrapper.dataset.mermaidRendered === "true" ||
            wrapper.dataset.mermaidRendering === "true"
        ) {
            return;
        }
        wrappers.push(wrapper);
    });
    if (wrappers.length === 0) return;
    if (mermaidRenderTimer) {
        clearTimeout(mermaidRenderTimer);
    }
    mermaidRenderTimer = setTimeout(() => {
        Promise.allSettled(wrappers.map(renderMermaidWrapper)).then(() => {
            let didScroll = false;
            if (!didScroll && window.__forceScrollToBottom) {
                didScroll = true;
                window.__forceScrollToBottom();
            }
            ensureMermaidInteractions(document);
        });
    }, 250);
};

const observeMermaid = () => {
    const target = document.getElementById("cards");
    if (!target) return;
    let upgradeTimer = null;
    const scheduleUpgrade = () => {
        if (upgradeTimer) return;
        upgradeTimer = setTimeout(() => {
            upgradeTimer = null;
            upgradeMermaidBlocks(target);
        }, 120);
    };
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type === "characterData") {
                const parent = mutation.target && mutation.target.parentElement;
                const markedRoot = parent ? parent.closest(".marked") : null;
                if (markedRoot) {
                    const rawText = markedRoot.getAttribute("data-raw") || "";
                    if (!isMermaidFenceClosed(rawText)) {
                        markedRoot.dataset.mermaidDirty = "true";
                    } else if (markedRoot.dataset.mermaidDirty === "true") {
                        markedRoot.dataset.mermaidDirty = "false";
                    }
                }
            }
        }
        scheduleUpgrade();
    });
    observer.observe(target, {
        childList: true,
        subtree: true,
        characterData: true,
    });
    upgradeMermaidBlocks(target);
};

window.__upgradeMermaidBlocks = upgradeMermaidBlocks;

document.addEventListener("DOMContentLoaded", () => {
    observeMermaid();
    setTimeout(() => upgradeMermaidBlocks(document), 0);
    setTimeout(() => ensureMermaidInteractions(document), 0);
});

document.body.addEventListener("htmx:afterSwap", (event) => {
    upgradeMermaidBlocks(event.target || document);
    ensureMermaidInteractions(event.target || document);
});

if (window.htmx && typeof window.htmx.onLoad === "function") {
    window.htmx.onLoad((root) => {
        upgradeMermaidBlocks(root || document);
        ensureMermaidInteractions(root || document);
    });
}
