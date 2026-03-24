import * as React from "react"

const cn = (...inputs: (string | undefined | null | false)[]) => inputs.filter(Boolean).join(" ")

export const Tabs = ({ children, defaultValue, className }: any) => {
    const [activeTab, setActiveTab] = React.useState(defaultValue);

    // Inject activeTab state into children
    const childrenWithProps = React.Children.map(children, child => {
        if (React.isValidElement(child)) {
            return React.cloneElement(child, { activeTab, setActiveTab } as any);
        }
        return child;
    });

    return <div className={className}>{childrenWithProps}</div>
}

export const TabsList = ({ children, className, activeTab, setActiveTab }: any) => (
    <div className={cn("inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground", className)}>
        {React.Children.map(children, child => {
            if (React.isValidElement(child)) {
                return React.cloneElement(child, { activeTab, setActiveTab } as any);
            }
            return child;
        })}
    </div>
)

export const TabsTrigger = ({ children, value, activeTab, setActiveTab, className }: any) => {
    const isActive = activeTab === value;
    return (
        <button
            type="button"
            onClick={() => setActiveTab(value)}
            className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50", isActive && "bg-background text-foreground shadow-sm", className)}
        >
            {children}
        </button>
    )
}

export const TabsContent = ({ children, value, activeTab, className }: any) => {
    if (value !== activeTab) return null;
    return <div className={cn("mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2", className)}>{children}</div>
}
