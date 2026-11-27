import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ensureMachine, ensurePort, run, waitRunning } from "./machine.ts";

const SERVER_PORT = 8787;
const SETUP_TIMEOUT_MS = 1_800_000;

function git(...args: string[]): string {
	return execFileSync("git", args, { encoding: "utf8" }).trim();
}

function publishedCommit(): string {
	if (git("status", "--porcelain") !== "") {
		throw new Error("Commit or discard local changes first. The Machine deploys a pushed commit.");
	}
	const commit = git("rev-parse", "HEAD");
	git("fetch", "--quiet", "origin");
	if (git("branch", "--remotes", "--contains", commit) === "") {
		throw new Error(`Push ${commit} first. The Machine clones it from origin.`);
	}
	return commit;
}

const commit = publishedCommit();

const machineId = await ensureMachine(process.env["POKER_HOUSE_MACHINE_ID"]);
console.log(`Machine ${machineId}`);
await waitRunning(machineId);

const port = await ensurePort(machineId, SERVER_PORT);
if (port.initial_access_key) {
	console.log(
		`Port key:  ${port.initial_access_key.access_key} (shown once, expires ${port.initial_access_key.expires_at})`,
	);
}
const hosts = [
	...new Set(
		[port.application_url, port.url]
			.filter((url) => url !== undefined)
			.map((url) => new URL(url).hostname),
	),
];

const setup = readFileSync(new URL("./setup.sh", import.meta.url), "utf8");
const { execution, output } = await run(
	machineId,
	["bash", "-s", "--", commit, ...hosts],
	setup,
	SETUP_TIMEOUT_MS,
);
if (execution.status !== "succeeded") {
	console.error(output.stderr);
	throw new Error(`Setup ended ${execution.status} with exit code ${execution.exit_code}.`);
}
console.log(output.stdout?.trim());
console.log(`Share URL: ${port.url ?? port.application_url}`);
console.log(`API URL:   ${port.application_url}`);
console.log(`Check:     curl -fsS -H "X-Dedalus-Port-Key: <port key>" ${port.application_url}`);
