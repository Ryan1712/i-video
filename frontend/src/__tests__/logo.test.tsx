import { render, screen } from "@testing-library/react";
import Logo from "@/components/Logo";

describe("Logo", () => {
  it("renders the Narro wordmark by default", () => {
    render(<Logo />);
    expect(screen.getByText("Narro")).toBeInTheDocument();
    expect(screen.getByText("N")).toBeInTheDocument();
  });

  it("hides the wordmark when withWordmark is false", () => {
    render(<Logo withWordmark={false} />);
    expect(screen.queryByText("Narro")).not.toBeInTheDocument();
  });
});
