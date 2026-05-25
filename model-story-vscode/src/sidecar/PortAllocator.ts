/**
 * Find a free TCP port starting from a preferred port.
 */
import * as net from "net";

/**
 * Returns the first free port >= `start`.
 * Tries up to `maxAttempts` ports before giving up.
 */
export async function findFreePort(
  start = 7860,
  maxAttempts = 20,
): Promise<number> {
  for (let port = start; port < start + maxAttempts; port++) {
    if (await _isFree(port)) return port;
  }
  throw new Error(
    `No free port found in range ${start}–${start + maxAttempts - 1}`,
  );
}

function _isFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, "127.0.0.1");
  });
}
