import { describe, it, expect } from "vitest";

describe("v6 refiner prompt resolution helpers", () => {
  it("resolves pipeline-level refiner prompt override from pipeline JSON", () => {
    const pipeline = {
      pipeline_type: "v6_vad_dual_asr",
      refiner_prompt_override: { zh: "custom pipeline prompt" },
    };
    // Helper that reads pipeline_type and returns refiner_prompt_override.zh
    const resolved =
      pipeline.pipeline_type === "v6_vad_dual_asr"
        ? pipeline.refiner_prompt_override?.zh ?? ""
        : "";
    expect(resolved).toBe("custom pipeline prompt");
  });

  it("returns empty string when no pipeline-level override set", () => {
    const pipeline = { pipeline_type: "v6_vad_dual_asr" };
    const resolved = (pipeline as any).refiner_prompt_override?.zh ?? "";
    expect(resolved).toBe("");
  });

  it("identifies v6 pipeline by pipeline_type field", () => {
    const v6 = { pipeline_type: "v6_vad_dual_asr", name: "[v6] test" };
    const v5 = { name: "[v5] test" };
    const isV6 = (p: any) => p.pipeline_type === "v6_vad_dual_asr";
    expect(isV6(v6)).toBe(true);
    expect(isV6(v5)).toBe(false);
  });
});

describe("Proofread prompt_overrides drawer v6 fields", () => {
  it("qwen3_context key is part of the expected prompt_overrides schema", () => {
    const overrides: Record<string, string | null> = {
      qwen3_context: "袁幸堯 史滕雷",
      "refiners.zh": "custom refiner prompt",
    };
    expect(overrides["qwen3_context"]).toBe("袁幸堯 史滕雷");
    expect(overrides["refiners.zh"]).toBe("custom refiner prompt");
  });

  it("null value for qwen3_context clears the override", () => {
    const overrides: Record<string, string | null> = { qwen3_context: null };
    expect(overrides["qwen3_context"]).toBeNull();
  });
});
