import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/reportView.test.ts"],
    fileParallelism: false,
    env: {
      JOURNEYMAN_OFFLINE: "1",
    },
  },
});
