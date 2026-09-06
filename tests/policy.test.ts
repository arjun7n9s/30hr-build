import { describe, expect, it } from "vitest";
import { checkTool, loadPolicy, pathAllowed } from "../src/policy.js";

const policy = loadPolicy();

describe("policy", () => {
  it("allows read tools", () => {
    expect(checkTool(policy, "issue_read", { issue_number: 1 }).ok).toBe(true);
    expect(checkTool(policy, "search_issues", { query: "bug" }).ok).toBe(true);
    expect(checkTool(policy, "get_file_contents", { path: "CONTRIBUTING.md" }).ok).toBe(true);
    expect(checkTool(policy, "get_file_contents", { path: "src/api/routes.py" }).ok).toBe(true);
  });

  it("denies writes, secrets, workflows, comments", () => {
    expect(checkTool(policy, "issue_write", { method: "create" }).ok).toBe(false);
    expect(checkTool(policy, "create_pull_request", {}).ok).toBe(false);
    expect(checkTool(policy, "add_issue_comment", {}).ok).toBe(false);
    expect(checkTool(policy, "delete_file", { path: "src/api/routes.py" }).ok).toBe(false);
    expect(checkTool(policy, "actions_run_trigger", {}).ok).toBe(false);
    expect(checkTool(policy, "push_files", {}).ok).toBe(false);
  });

  it("blocks files outside the allowlist", () => {
    expect(pathAllowed(policy, "README.md")).toBe(false);
    expect(checkTool(policy, "get_file_contents", { path: "README.md" }).ok).toBe(false);
    expect(checkTool(policy, "get_file_contents", { path: ".env" }).ok).toBe(false);
    expect(checkTool(policy, "get_file_contents", { path: "" }).ok).toBe(false);
  });
});
