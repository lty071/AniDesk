import { describe, expect, it } from "vitest";
import { validPlaybackUrl } from "./platform";

describe("playback URL validation", () => {
  it("accepts HTTP and HTTPS only", () => {
    expect(validPlaybackUrl("https://example.com/watch/1")).toBe(true);
    expect(validPlaybackUrl("http://localhost:8080/video")).toBe(true);
    expect(validPlaybackUrl("javascript:alert(1)")).toBe(false);
    expect(validPlaybackUrl("file:///C:/video.mp4")).toBe(false);
    expect(validPlaybackUrl("not a url")).toBe(false);
  });
});
