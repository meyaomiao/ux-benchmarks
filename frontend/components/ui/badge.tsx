import { cn } from "@/lib/utils";

const VARIANTS: Record<string, string> = {
  default: "bg-gray-100 text-gray-600",
  direct: "bg-indigo-50 text-indigo-700",
  indirect: "bg-sky-50 text-sky-700",
  cross_industry: "bg-amber-50 text-amber-700",
  confirmed: "bg-green-50 text-green-700",
  pending: "bg-amber-50 text-amber-700",
  excluded: "bg-gray-100 text-gray-400",
  active: "bg-green-50 text-green-700",
  deprecated: "bg-gray-100 text-gray-400",
};

export function Badge({
  variant = "default",
  children,
  className,
}: {
  variant?: keyof typeof VARIANTS | string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium",
        VARIANTS[variant] || VARIANTS.default,
        className
      )}
    >
      {children}
    </span>
  );
}
