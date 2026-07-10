import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SeriesPage from "@/app/dashboard/series/page";
import * as apiModule from "@/lib/api";

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn() }) }));
jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => <a href={href} {...rest}>{children}</a> }));
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));

const mockedApi = jest.mocked(apiModule.api);

beforeEach(() => jest.clearAllMocks());

describe("SeriesPage", () => {
  it("lists series from the API", async () => {
    mockedApi.get.mockResolvedValueOnce([
      { id: 1, name: "Zombie apocalypse", description: "", style: {}, episode_count: 3 },
    ]);
    render(<SeriesPage />);
    expect(await screen.findByText("Zombie apocalypse")).toBeInTheDocument();
    expect(screen.getByText(/3 episodes/i)).toBeInTheDocument();
  });

  it("creates a series with language and style bible", async () => {
    mockedApi.get.mockResolvedValueOnce([]);
    mockedApi.post.mockResolvedValueOnce({ id: 9, name: "New S", description: "", style: {}, episode_count: 0 });
    mockedApi.get.mockResolvedValueOnce([{ id: 9, name: "New S", description: "", style: {}, episode_count: 0 }]);

    const user = userEvent.setup();
    render(<SeriesPage />);
    await user.click(await screen.findByRole("button", { name: /new series/i }));
    await user.type(screen.getByPlaceholderText(/series name/i), "New S");
    await user.type(screen.getByPlaceholderText(/style bible/i), "black stick figures");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => {
      expect(mockedApi.post).toHaveBeenCalledWith("/series", {
        name: "New S",
        description: "",
        style: { language: "en", image_style_bible: "black stick figures", voice_id: "" },
      });
    });
  });
});
