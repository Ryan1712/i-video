import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ScriptPanel from "@/components/episode/ScriptPanel";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));

const mockedApi = jest.mocked(apiModule.api);

beforeEach(() => jest.clearAllMocks());

function setup(overrides: Partial<Parameters<typeof ScriptPanel>[0]> = {}) {
  const onEpisodeUpdated = jest.fn();
  render(
    <ScriptPanel
      episodeId={5}
      initialBrief=""
      initialDurationSec={null}
      initialScript=""
      disabled={false}
      onEpisodeUpdated={onEpisodeUpdated}
      {...overrides}
    />
  );
  return { onEpisodeUpdated };
}

describe("ScriptPanel", () => {
  it("generates a script from brief + duration", async () => {
    mockedApi.post.mockResolvedValueOnce({ script: "Generated narration." });
    const user = userEvent.setup();
    setup();

    await user.type(screen.getByPlaceholderText(/episode idea/i), "zombie outbreak");
    await user.clear(screen.getByLabelText(/minutes/i));
    await user.type(screen.getByLabelText(/minutes/i), "8");
    await user.click(screen.getByRole("button", { name: /generate script/i }));

    await waitFor(() => {
      expect(mockedApi.post).toHaveBeenCalledWith("/episodes/5/generate-script", {
        brief: "zombie outbreak",
        target_duration_sec: 480,
      });
    });
    expect(await screen.findByDisplayValue("Generated narration.")).toBeInTheDocument();
  });

  it("analyzes the edited script into scenes", async () => {
    mockedApi.post.mockResolvedValueOnce({ id: 5, scenes: [] });
    const user = userEvent.setup();
    const { onEpisodeUpdated } = setup({ initialScript: "Existing script." });

    await user.click(screen.getByRole("button", { name: /split into scenes/i }));

    await waitFor(() => {
      expect(mockedApi.post).toHaveBeenCalledWith("/episodes/5/analyze-script", {
        script: "Existing script.",
      });
      expect(onEpisodeUpdated).toHaveBeenCalled();
    });
  });

  it("shows a friendly error on ERR_SCRIPT_GENERATION_FAILED", async () => {
    mockedApi.post.mockRejectedValueOnce(new ApiError(502, "ERR_SCRIPT_GENERATION_FAILED"));
    const user = userEvent.setup();
    setup();

    await user.type(screen.getByPlaceholderText(/episode idea/i), "x");
    await user.click(screen.getByRole("button", { name: /generate script/i }));

    expect(await screen.findByText(/script generation failed/i)).toBeInTheDocument();
  });
});
