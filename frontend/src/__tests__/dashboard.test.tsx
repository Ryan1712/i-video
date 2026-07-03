import { render, screen, waitFor } from "@testing-library/react";
import DashboardPage from "@/app/dashboard/page";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api";

jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => <a href={href} {...rest}>{children}</a> }));
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));

const mockedApi = jest.mocked(apiModule.api);

// Silence localStorage errors in jsdom
Object.defineProperty(window, "localStorage", {
  value: { getItem: () => "fake-token", setItem: jest.fn(), removeItem: jest.fn() },
});

beforeEach(() => jest.clearAllMocks());

const EPISODES = [
  { id: 1, title: "What If the Internet Went Dark?", description: "", status: "built", output_object_key: "ep1/output.mp4", youtube_video_id: null, scenes: [{ id: 1 }, { id: 2 }] },
  { id: 2, title: "What If Mars Had Water?", description: "", status: "draft", output_object_key: null, youtube_video_id: null, scenes: [{ id: 3 }] },
];

describe("DashboardPage", () => {
  it("shows loading spinner initially", () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));
    render(<DashboardPage />);
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("renders episode list after loading", async () => {
    mockedApi.get.mockResolvedValueOnce(EPISODES);
    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("What If the Internet Went Dark?")).toBeInTheDocument();
      expect(screen.getByText("What If Mars Had Water?")).toBeInTheDocument();
    });
  });

  it("shows episode count in subtitle", async () => {
    mockedApi.get.mockResolvedValueOnce(EPISODES);
    render(<DashboardPage />);

    await waitFor(() => expect(screen.getByText("2 episodes")).toBeInTheDocument());
  });

  it("shows 'Built' badge for built episodes", async () => {
    mockedApi.get.mockResolvedValueOnce(EPISODES);
    render(<DashboardPage />);

    await waitFor(() => expect(screen.getByText("Built")).toBeInTheDocument());
  });

  it("shows 'Draft' badge for draft episodes", async () => {
    mockedApi.get.mockResolvedValueOnce(EPISODES);
    render(<DashboardPage />);

    await waitFor(() => expect(screen.getByText("Draft")).toBeInTheDocument());
  });

  it("shows empty state when no episodes", async () => {
    mockedApi.get.mockResolvedValueOnce([]);
    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText("No episodes yet")).toBeInTheDocument()
    );
  });

  it("shows error message on API failure", async () => {
    mockedApi.get.mockRejectedValueOnce(new ApiError(500, "Server Error"));
    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText("Failed to load episodes.")).toBeInTheDocument()
    );
  });

  it("redirects to login on 401", async () => {
    const assign = jest.fn();
    Object.defineProperty(window, "location", { value: { href: "" }, writable: true });
    mockedApi.get.mockRejectedValueOnce(new ApiError(401, "Unauthorized"));
    render(<DashboardPage />);

    await waitFor(() => expect(window.location.href).toBe("/login"));
  });

  it("links to episode detail page", async () => {
    mockedApi.get.mockResolvedValueOnce(EPISODES);
    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /what if the internet/i })).toHaveAttribute("href", "/dashboard/episodes/1");
    });
  });

  it("shows 'New episode' link", async () => {
    mockedApi.get.mockResolvedValueOnce([]);
    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /new episode/i })).toHaveAttribute("href", "/dashboard/episodes/new");
    });
  });
});
