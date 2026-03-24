import * as React from "react"
// Simplified Label because Radix UI is complicated to implement from scratch without deps
// This is a minimal mock to satisfy imports and render a label
const cn = (...inputs: (string | undefined | null | false)[]) => inputs.filter(Boolean).join(" ")

const Label = React.forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(({ className, ...props }, ref) => (
    <label
        ref={ref}
        className={cn(
            "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
            className
        )}
        {...props}
    />
))
Label.displayName = "Label"

export { Label }
