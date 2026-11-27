interface Env {
  readonly ASSETS: Fetcher;
  readonly API_ORIGIN: string;
  readonly PORT_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/')) {
      const upstream = new Request(
        env.API_ORIGIN + url.pathname + url.search,
        request,
      );
      upstream.headers.set('X-Dedalus-Port-Key', env.PORT_KEY);
      upstream.headers.delete('Cookie');
      return fetch(upstream);
    }
    return new Response('Not found', {status: 404});
  },
} satisfies ExportedHandler<Env>;
