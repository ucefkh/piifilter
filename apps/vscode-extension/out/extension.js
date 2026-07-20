"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
let statusBar;
// ── Configuration ────────────────────────────────────────────────────────────
function getConfig() {
    const config = vscode.workspace.getConfiguration('piifilter');
    return {
        serverUrl: config.get('serverUrl', 'http://127.0.0.1:8000'),
        mode: config.get('mode', 'semantic'),
        enabled: config.get('enabled', true),
    };
}
async function filterText(text) {
    if (!text || text.trim().length === 0)
        return text;
    const { serverUrl, mode } = getConfig();
    try {
        const res = await fetch(`${serverUrl}/v1/filter`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: text, mode }),
        });
        if (!res.ok) {
            console.warn(`[PIIFilter] API returned ${res.status}: ${res.statusText}`);
            return text;
        }
        const data = await res.json();
        if (data.blocked) {
            vscode.window.showWarningMessage(`PIIFilter blocked: ${data.block_reason || 'Policy violation'}`);
            return '[PIIFilter: Content blocked by policy]';
        }
        return data.filtered || text;
    }
    catch (err) {
        // Server offline — pass through transparently
        return text;
    }
}
// ── Debounce helper ──────────────────────────────────────────────────────────
function debounce(fn, delay) {
    let timer;
    return (e) => {
        if (timer)
            clearTimeout(timer);
        timer = setTimeout(() => fn(e), delay);
    };
}
// ── Activation ───────────────────────────────────────────────────────────────
function activate(context) {
    // ── Status bar ───────────────────────────────────────────────────────────
    statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBar.command = 'piifilter.showStatus';
    statusBar.text = '$(shield) PIIFilter';
    statusBar.tooltip = 'PIIFilter: Checking server…';
    statusBar.show();
    context.subscriptions.push(statusBar);
    // ── Health-check loop ────────────────────────────────────────────────────
    async function updateStatus() {
        const cfg = getConfig();
        if (!cfg.enabled) {
            statusBar.text = '$(shield) PIIFilter (off)';
            statusBar.tooltip = 'PIIFilter: Disabled';
            statusBar.backgroundColor = undefined;
            return;
        }
        try {
            const res = await fetch(`${cfg.serverUrl}/v1/health`);
            if (res.ok) {
                statusBar.text = '$(shield) PIIFilter';
                statusBar.tooltip = `PIIFilter: Connected (${cfg.mode})`;
                statusBar.backgroundColor = undefined;
            }
            else {
                statusBar.text = '$(shield) PIIFilter';
                statusBar.tooltip = `PIIFilter: Server unhealthy (${res.status})`;
                statusBar.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
            }
        }
        catch {
            statusBar.text = '$(shield-x) PIIFilter';
            statusBar.tooltip = 'PIIFilter: Server offline';
            statusBar.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
        }
    }
    updateStatus();
    const healthInterval = setInterval(updateStatus, 30_000);
    context.subscriptions.push({ dispose: () => clearInterval(healthInterval) });
    // Re-check when settings change
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e) => {
        if (e.affectsConfiguration('piifilter'))
            updateStatus();
    }));
    // ── Register command ─────────────────────────────────────────────────────
    context.subscriptions.push(vscode.commands.registerCommand('piifilter.showStatus', () => {
        const { serverUrl, mode, enabled } = getConfig();
        vscode.window.showInformationMessage(`PIIFilter: ${enabled ? 'Enabled' : 'Disabled'}` +
            ` | Server: ${serverUrl}` +
            ` | Mode: ${mode}`);
    }));
    // ── Intercept document changes (debounced) ───────────────────────────────
    // This catches content typed while an AI assistant is active.
    // When the user's text contains PII, the filter replaces it inline.
    const debouncedFilter = debounce(async (e) => {
        const cfg = getConfig();
        if (!cfg.enabled)
            return;
        // Only intercept if the change is meaningful (not whitespace-only)
        const doc = e.document;
        if (doc.uri.scheme !== 'file' && doc.uri.scheme !== 'untitled')
            return;
        // Look at the last changed line – this is likely the active edit
        // that an AI coding assistant would pick up.
        const change = e.contentChanges[e.contentChanges.length - 1];
        if (!change || change.text.trim().length === 0)
            return;
        const filtered = await filterText(change.text);
        if (filtered !== change.text) {
            // The filter replaced sensitive content; apply inline edit.
            // We use a TextEdit to swap only the affected range.
            const edit = new vscode.WorkspaceEdit();
            edit.replace(doc.uri, change.range, filtered);
            vscode.workspace.applyEdit(edit);
        }
    }, 500);
    context.subscriptions.push(vscode.workspace.onDidChangeTextDocument(debouncedFilter));
    // ── Intercept on-save text (catches side-effect writes) ──────────────────
    context.subscriptions.push(vscode.workspace.onWillSaveTextDocument(async (e) => {
        const cfg = getConfig();
        if (!cfg.enabled)
            return;
        if (e.document.uri.scheme !== 'file')
            return;
        const text = e.document.getText();
        if (text.length === 0)
            return;
        const filtered = await filterText(text);
        if (filtered !== text) {
            // Replace entire document content with filtered version
            e.waitUntil(Promise.resolve([
                vscode.TextEdit.replace(new vscode.Range(0, 0, e.document.lineCount, 0), filtered),
            ]));
        }
    }));
    // ── Active editor text provider (for selection-based filtering) ──────────
    context.subscriptions.push(vscode.window.onDidChangeTextEditorSelection(async (e) => {
        const cfg = getConfig();
        if (!cfg.enabled)
            return;
        const editor = e.textEditor;
        const selection = editor.selection;
        if (selection.isEmpty)
            return;
        // If user selects text, offer quick-pick to filter it
        const selectedText = editor.document.getText(selection);
        if (!selectedText || selectedText.length > 5000)
            return;
        const filtered = await filterText(selectedText);
        if (filtered !== selectedText) {
            // Only replace if the content actually changed
            const edit = new vscode.WorkspaceEdit();
            edit.replace(editor.document.uri, selection, filtered);
            vscode.workspace.applyEdit(edit);
        }
    }));
    console.log('[PIIFilter] Extension activated');
}
function deactivate() {
    console.log('[PIIFilter] Extension deactivated');
}
