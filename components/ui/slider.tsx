import * as React from "react"
// Simplified Slider 
const cn = (...inputs: (string | undefined | null | false)[]) => inputs.filter(Boolean).join(" ")

const Slider = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
    <input
        type="range"
        ref={ref}
        className={cn(
            "relative flex w-full touch-none select-none items-center",
            className
        )}
        {...props}
    />
))
Slider.displayName = "Slider"

export { Slider }
