class SilentEventSource {
  onmessage = null;
  close(): void {
    this.onmessage = null;
  }
}

Object.defineProperty(globalThis, 'EventSource', {value: SilentEventSource});
