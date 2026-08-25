console.log(
  JSON.stringify({
    timestamp: new Date().toISOString(),
    level: "info",
    service: "web",
    event: "web_started",
    environment: process.env.ANDYHUB_ENVIRONMENT ?? "unknown",
  }),
);

await import("./server.js");
