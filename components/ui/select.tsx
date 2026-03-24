import * as React from "react"

// Simplified Select because Radix UI is complicated to implement from scratch without deps
// This is a minimal mock to satisfy imports and render a native select or div
export const Select = ({ children, onValueChange, defaultValue }: any) => {
    return <div className="relative inline-block w-full">{children}</div>
}
export const SelectTrigger = ({ children, className }: any) => <button className={`flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}>{children}</button>
export const SelectValue = ({ placeholder }: any) => <span>{placeholder}</span>
export const SelectContent = ({ children }: any) => <div className="absolute z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md animate-in fade-in-80">{children}</div>
export const SelectItem = ({ children, value }: any) => <div className="relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50">{children}</div>
