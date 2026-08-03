import * as os from "os";
import * as vscode from "vscode";

import { uriPreservingQuery } from "../util/uri";

const ISSUE_URL = "https://github.com/Epochix-dev/epochix/issues/new";

/**
 * Open a prefilled GitHub issue with the diagnostics we would otherwise ask
 * the reporter to gather by hand.
 *
 * Deliberately includes NO run name, file path or log content: those come from
 * the reporter's own training, and a bug report should not be the thing that
 * leaks a project name into a public issue. What is here is the environment,
 * which is what actually narrows a bug down.
 */
export function registerReportBug(
  context: vscode.ExtensionContext,
  getSidecarVersion: () => string | undefined,
): vscode.Disposable {
  return vscode.commands.registerCommand("epochix.reportBug", async () => {
    const ext = context.extension.packageJSON as { version?: string };
    const sidecar = getSidecarVersion();

    const body = [
      "### What happened?",
      "",
      "",
      "### What did you expect instead?",
      "",
      "",
      "### Steps to reproduce",
      "",
      "1. ",
      "",
      "---",
      "",
      "<details><summary>Environment (filled in automatically)</summary>",
      "",
      "```",
      `extension    ${ext.version ?? "unknown"}`,
      `vscode       ${vscode.version}`,
      `platform     ${process.platform} ${os.release()} (${process.arch})`,
      `node         ${process.versions.node}`,
      // The single most useful line: a stale Python package silently degrades
      // the whole product, and it has been the cause more than once.
      `python pkg   ${sidecar ?? "not reachable (standalone mode)"}`,
      `trusted      ${vscode.workspace.isTrusted}`,
      "```",
      "",
      "</details>",
      "",
      "_No run name, file path or log content is included._",
    ].join("\n");

    const url =
      `${ISSUE_URL}?labels=bug` +
      `&title=${encodeURIComponent("Extension: ")}` +
      `&body=${encodeURIComponent(body)}`;

    await vscode.env.openExternal(uriPreservingQuery(url));
  });
}
