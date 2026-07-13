import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SignupPage from "@/app/[locale]/(auth)/signup/page";
import * as auth from "@/lib/auth";
import { ApiError } from "@/lib/api";

const mockPush = jest.fn();
jest.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => <a href={href} {...rest}>{children}</a>,
}));
jest.mock("@/lib/auth");

const mockedSignup = jest.mocked(auth.signup);

beforeEach(() => jest.clearAllMocks());

function setup() {
  const user = userEvent.setup();
  render(<SignupPage />);
  return {
    user,
    emailInput: screen.getByPlaceholderText("you@example.com"),
    passwordInput: screen.getByPlaceholderText("Min. 8 characters"),
    confirmInput: screen.getByPlaceholderText("••••••••"),
    submitButton: screen.getByRole("button", { name: /create account/i }),
  };
}

describe("SignupPage", () => {
  it("renders all form fields", () => {
    const { emailInput, passwordInput, confirmInput, submitButton } = setup();
    expect(emailInput).toBeInTheDocument();
    expect(passwordInput).toBeInTheDocument();
    expect(confirmInput).toBeInTheDocument();
    expect(submitButton).toBeInTheDocument();
  });

  it("shows error when passwords do not match", async () => {
    const { user, emailInput, passwordInput, confirmInput, submitButton } = setup();

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "password123");
    await user.type(confirmInput, "different456");
    await user.click(submitButton);

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    expect(mockedSignup).not.toHaveBeenCalled();
  });

  it("shows error when password is too short", async () => {
    const { user, emailInput, passwordInput, confirmInput, submitButton } = setup();

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "short");
    await user.type(confirmInput, "short");
    await user.click(submitButton);

    expect(screen.getByText("Password must be at least 8 characters.")).toBeInTheDocument();
    expect(mockedSignup).not.toHaveBeenCalled();
  });

  it("calls signup and redirects to /dashboard on success", async () => {
    mockedSignup.mockResolvedValueOnce(undefined);
    const { user, emailInput, passwordInput, confirmInput, submitButton } = setup();

    await user.type(emailInput, "new@example.com");
    await user.type(passwordInput, "password123");
    await user.type(confirmInput, "password123");
    await user.click(submitButton);

    await waitFor(() => {
      expect(mockedSignup).toHaveBeenCalledWith("new@example.com", "password123");
      expect(mockPush).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("shows 'already exists' message on 409", async () => {
    mockedSignup.mockRejectedValueOnce(new ApiError(409, "Conflict"));
    const { user, emailInput, passwordInput, confirmInput, submitButton } = setup();

    await user.type(emailInput, "existing@example.com");
    await user.type(passwordInput, "password123");
    await user.type(confirmInput, "password123");
    await user.click(submitButton);

    await waitFor(() =>
      expect(
        screen.getByText("An account with this email already exists.")
      ).toBeInTheDocument()
    );
  });
});
