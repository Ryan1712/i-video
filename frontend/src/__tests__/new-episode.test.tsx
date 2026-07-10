import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewEpisodePage from "@/app/dashboard/episodes/new/page";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api";

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
}));
jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => <a href={href} {...rest}>{children}</a> }));
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));
Object.defineProperty(window, "localStorage", {
  value: { getItem: () => "fake-token", setItem: jest.fn(), removeItem: jest.fn() },
});

const mockedApi = jest.mocked(apiModule.api);

beforeEach(() => {
  jest.clearAllMocks();
  mockedApi.get.mockResolvedValue([]);
});

async function setup() {
  const user = userEvent.setup();
  await act(async () => {
    render(<NewEpisodePage />);
  });
  return {
    user,
    titleInput: screen.getByPlaceholderText(/what if the internet/i),
    submitButton: screen.getByRole("button", { name: /create episode/i }),
  };
}

describe("NewEpisodePage", () => {
  it("renders title, description, tags, and zero scenes by default", async () => {
    await setup();
    expect(screen.getByPlaceholderText(/what if the internet/i)).toBeInTheDocument();
    expect(screen.getByText(/scenes \(0\)/i)).toBeInTheDocument();
  });

  it("adds a scene when 'Add scene' is clicked", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: /add scene/i }));
    expect(screen.getByText(/scenes \(1\)/i)).toBeInTheDocument();
  });

  it("removes a scene when remove button is clicked, including the last one", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: /add scene/i }));
    expect(screen.getByText(/scenes \(1\)/i)).toBeInTheDocument();

    const allButtons = screen.getAllByRole("button");
    const removeBtn = allButtons.find((b) => b.querySelector("svg") && b !== screen.getByRole("button", { name: /create episode/i }) && b !== screen.getByRole("button", { name: /add scene/i }));
    expect(removeBtn).toBeTruthy();
    if (removeBtn) {
      await user.click(removeBtn);
      expect(screen.getByText(/scenes \(0\)/i)).toBeInTheDocument();
    }
  });

  it("allows creating an episode with zero scenes", async () => {
    const { user, titleInput } = await setup();
    await user.type(titleInput, "What If Everything Changed?");
    mockedApi.post.mockResolvedValueOnce({ id: 7 });
    await user.click(screen.getByRole("button", { name: /create episode/i }));
    await waitFor(() => {
      expect(screen.queryByText("All scenes need narration text.")).not.toBeInTheDocument();
      expect(mockPush).toHaveBeenCalledWith("/dashboard/episodes/7");
    });
  });

  it("shows validation error if a scene has empty narration", async () => {
    const { user, titleInput } = await setup();
    await user.type(titleInput, "What If Everything Changed?");
    await user.click(screen.getByRole("button", { name: /add scene/i }));
    await user.click(screen.getByRole("button", { name: /create episode/i }));
    await waitFor(() =>
      expect(screen.getByText("All scenes need narration text.")).toBeInTheDocument()
    );
  });

  it("posts to /episodes and redirects on success", async () => {
    mockedApi.post.mockResolvedValueOnce({ id: 42 });
    const { user, titleInput } = await setup();

    await user.type(titleInput, "What If Everything Changed?");
    await user.click(screen.getByRole("button", { name: /create episode/i }));

    await waitFor(() => {
      expect(mockedApi.post).toHaveBeenCalledWith("/episodes", expect.objectContaining({
        title: "What If Everything Changed?",
        series_id: null,
        scenes: [],
      }));
      expect(mockPush).toHaveBeenCalledWith("/dashboard/episodes/42");
    });
  });

  it("posts scenes when added explicitly", async () => {
    mockedApi.post.mockResolvedValueOnce({ id: 43 });
    const { user, titleInput } = await setup();

    await user.type(titleInput, "What If Everything Changed?");
    await user.click(screen.getByRole("button", { name: /add scene/i }));
    await user.type(screen.getByPlaceholderText(/narration for scene 1/i), "Scene one narration text here.");
    await user.click(screen.getByRole("button", { name: /create episode/i }));

    await waitFor(() => {
      expect(mockedApi.post).toHaveBeenCalledWith("/episodes", expect.objectContaining({
        title: "What If Everything Changed?",
        series_id: null,
        scenes: [{ narration_text: "Scene one narration text here." }],
      }));
      expect(mockPush).toHaveBeenCalledWith("/dashboard/episodes/43");
    });
  });

  it("shows API error message on failure", async () => {
    mockedApi.post.mockRejectedValueOnce(new ApiError(422, "Validation error"));
    const { user, titleInput } = await setup();

    await user.type(titleInput, "Test Episode");
    await user.click(screen.getByRole("button", { name: /create episode/i }));

    await waitFor(() =>
      expect(screen.getByText("Validation error")).toBeInTheDocument()
    );
  });
});
