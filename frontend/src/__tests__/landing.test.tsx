import { render, screen } from "@testing-library/react";
import Hero from "@/components/landing/Hero";
import HowItWorks from "@/components/landing/HowItWorks";
import Features from "@/components/landing/Features";

describe("Landing copy (EN via mocked useTranslations)", () => {
  it("hero sells the series positioning, not generic AI video", () => {
    render(<Hero />);
    expect(screen.getByText("Turn one idea into a whole series")).toBeInTheDocument();
    expect(screen.getByText(/from our pilot episode/i)).toBeInTheDocument();
    expect(screen.queryByText(/editing skills/i)).not.toBeInTheDocument();
  });

  it("how-it-works shows the real 4-step pipeline", () => {
    render(<HowItWorks />);
    expect(screen.getByText(/Drop in your idea/i)).toBeInTheDocument();
    expect(screen.getByText(/AI writes the script — you approve it/i)).toBeInTheDocument();
  });

  it("features never promise a timeline editor", () => {
    render(<Features />);
    expect(screen.queryByText(/timeline/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Series asset library/i)).toBeInTheDocument();
  });
});
