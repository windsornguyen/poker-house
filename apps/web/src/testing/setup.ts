class SilentEventSource {
  onmessage = null;
  addEventListener(): void {
    this.onmessage = null;
  }
  close(): void {
    this.onmessage = null;
  }
}

Object.defineProperty(globalThis, 'EventSource', {value: SilentEventSource});
