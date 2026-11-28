import * as React from 'react';
import {cn} from 'cn';

function Input({className, type, ...props}: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'h-8 w-full min-w-0 rounded-lg border border-input bg-card px-2.5 py-1 text-base shadow-2xs transition-[border-color,box-shadow,background-color] duration-150 ease-out outline-none motion-reduce:transition-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground hover:not-disabled:not-focus-visible:border-foreground/35 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/25 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-muted/60 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-background/80 dark:shadow-[inset_0_1px_2px_0_rgb(0_0_0/0.4)] dark:disabled:bg-muted/40 dark:aria-invalid:border-destructive/60 dark:aria-invalid:ring-destructive/35',
        className,
      )}
      {...props}
    />
  );
}

export {Input};
