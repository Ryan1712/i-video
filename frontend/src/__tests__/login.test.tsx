import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginPage from "@/app/[locale]/(auth)/login/page";
import * as auth from "@/lib/auth";
import { ApiError } from "@/lib/api";

const mockPush = jest.fn();
jest.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => <a href={href} {...rest}>{children}</a>,
}));
jest.mock("@/lib/auth");

const mockedLogin = jest.mocked(auth.login);

beforeEach(() => {
  jest.clearAllMocks();
});

function setup() {
  const user = userEvent.setup();
  render(<LoginPage />);
  return {
    user,
    emailInput: screen.getByPlaceholderText("you@example.com"),
    passwordInput: screen.getByPlaceholderText("••••••••"),
    submitButton: screen.getByRole("button", { name: /sign in/i }),
  };
}

describe("LoginPage", () => {
  it("renders email and password fields", () => {
    const { emailInput, passwordInput, submitButton } = setup();
    expect(emailInput).toBeInTheDocument();
    expect(passwordInput).toBeInTheDocument();
    expect(submitButton).toBeInTheDocument();
  });

  it("calls login with email and password on submit", async () => {
    mockedLogin.mockResolvedValueOnce(undefined);
    const { user, emailInput, passwordInput, submitButton } = setup();

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "secret123");
    await user.click(submitButton);

    await waitFor(() => {
      expect(mockedLogin).toHaveBeenCalledWith("test@example.com", "secret123");
    });
  });

  it("redirects to /dashboard after successful login", async () => {
    mockedLogin.mockResolvedValueOnce(undefined);
    const { user, emailInput, passwordInput, submitButton } = setup();

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "secret123");
    await user.click(submitButton);

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows 'Invalid email or password' on 401", async () => {
    mockedLogin.mockRejectedValueOnce(new ApiError(401, "Unauthorized"));
    const { user, emailInput, passwordInput, submitButton } = setup();

    await user.type(emailInput, "bad@example.com");
    await user.type(passwordInput, "wrongpass");
    await user.click(submitButton);

    await waitFor(() =>
      expect(screen.getByText("Invalid email or password.")).toBeInTheDocument()
    );
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("shows server error message on non-401 API error", async () => {
    mockedLogin.mockRejectedValueOnce(new ApiError(500, "Internal Server Error"));
    const { user, emailInput, passwordInput, submitButton } = setup();

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "pass1234");
    await user.click(submitButton);

    await waitFor(() =>
      expect(screen.getByText("Internal Server Error")).toBeInTheDocument()
    );
  });

  it("disables submit button while loading", async () => {
    let resolve!: () => void;
    mockedLogin.mockReturnValueOnce(new Promise<void>((r) => { resolve = r; }));
    const { user, emailInput, passwordInput, submitButton } = setup();

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "pass1234");
    await user.click(submitButton);

    expect(submitButton).toBeDisabled();
    resolve();
  });
});
