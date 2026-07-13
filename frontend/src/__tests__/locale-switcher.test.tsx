import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LocaleSwitcher from "@/components/LocaleSwitcher";

const mockReplace = jest.fn();
jest.mock("@/i18n/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ replace: mockReplace }),
}));

beforeEach(() => jest.clearAllMocks());

describe("LocaleSwitcher", () => {
  it("renders EN and VI options", () => {
    render(<LocaleSwitcher />);
    expect(screen.getByRole("button", { name: "EN" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "VI" })).toBeInTheDocument();
  });

  it("switches to vi keeping the current path", async () => {
    const user = userEvent.setup();
    render(<LocaleSwitcher />);
    await user.click(screen.getByRole("button", { name: "VI" }));
    expect(mockReplace).toHaveBeenCalledWith("/dashboard", { locale: "vi" });
  });
});
