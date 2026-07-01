/**
 * 轻量 Markdown 渲染 (port of chat.js renderMd).
 * 额外把 [[label|action]] 渲染为可触发地图联动的链接。
 *
 * 安全:AI 输出按不可信内容处理 —— action 走白名单,属性做 HTML 转义,
 * 最终经 DOMPurify 净化后才交给 dangerouslySetInnerHTML。
 */
import DOMPurify from "dompurify";

function escapeHtml(t: string): string {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttr(t: string): string {
  return escapeHtml(t).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/** 只允许已知前缀 + 受限字符的 action,其余一律降级为纯文本(不渲染成链接)。 */
function normalizeAction(raw: string): string | null {
  const a = raw.replace(/&amp;/g, "&").trim();
  if (/^fly:[A-Za-z0-9_-]{1,80}$/.test(a)) return a;
  if (/^log:\d{4}-\d{2}-\d{2}$/.test(a)) return a;
  if (/^(t|c|l|s|kw):[一-龥A-Za-z0-9_ -]{1,60}$/.test(a)) return a;
  if (/^3d:[01]$/.test(a)) return a;
  return null;
}

const ALLOWED_TAGS = ["a", "br", "strong", "em", "code", "h4", "h5", "hr", "ul", "ol", "li"];
const ALLOWED_ATTR = ["class", "title", "data-action"];

export function renderChatMarkdown(text: string): string {
  let h = escapeHtml(text);

  h = h.replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, (_, label, action) => {
    const safeAction = normalizeAction(String(action));
    if (!safeAction) return String(label);
    const isLog = safeAction.startsWith("log:");
    const icon = isLog ? " 📋" : " 📍";
    const tip = isLog ? "查看工作日志" : "在地图上查看";
    const cls = isLog ? "cf cf-log" : "cf";
    return `<a class="${cls}" data-action="${escapeAttr(safeAction)}" title="${tip}">${label}${icon}</a>`;
  });

  h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  h = h.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");
  h = h.replace(/^####\s+(.+)$/gm, "<h5>$1</h5>");
  h = h.replace(/^###\s+(.+)$/gm, "<h4>$1</h4>");
  h = h.replace(/^##\s+(.+)$/gm, "<h4>$1</h4>");
  h = h.replace(/^#\s+(.+)$/gm, "<h4>$1</h4>");
  h = h.replace(/^---+$/gm, "<hr>");
  h = h.replace(/`([^`]+)`/g, "<code>$1</code>");

  const lines = h.split("\n");
  const out: string[] = [];
  let inList = false;
  let listType: "ul" | "ol" = "ul";
  for (const li of lines) {
    const ulMatch = li.match(/^[-·•]\s+(.+)/);
    const olMatch = li.match(/^(\d+)[.、]\s*(.+)/);
    if (ulMatch) {
      if (!inList || listType !== "ul") {
        if (inList) out.push(`</${listType}>`);
        out.push("<ul>");
        inList = true;
        listType = "ul";
      }
      out.push("<li>" + ulMatch[1] + "</li>");
    } else if (olMatch) {
      if (!inList || listType !== "ol") {
        if (inList) out.push(`</${listType}>`);
        out.push("<ol>");
        inList = true;
        listType = "ol";
      }
      out.push("<li>" + olMatch[2] + "</li>");
    } else {
      if (inList) {
        out.push(`</${listType}>`);
        inList = false;
      }
      out.push(li);
    }
  }
  if (inList) out.push(`</${listType}>`);

  let body = out.join("\n").replace(/\n/g, "<br>");
  body = body.replace(/<br>(<\/?(?:ul|ol|li|h[345]|hr))/g, "$1");
  body = body.replace(/(<\/(?:ul|ol|li|h[345]|hr)>)<br>/g, "$1");
  body = body.replace(/(<(?:ul|ol|hr)[^>]*>)<br>/g, "$1");
  return DOMPurify.sanitize(body, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
  });
}

export function escapeStreamPreview(text: string): string {
  return escapeHtml(text).replace(/\n/g, "<br>");
}
