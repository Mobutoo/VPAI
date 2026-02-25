declare global {
	// Scheduler guard: prevents double-start during SvelteKit HMR restarts
	var __palaisSchedulersStarted: boolean | undefined;

	namespace App {
		interface Locals {
			user: {
				authenticated: boolean;
				source: 'api' | 'cookie' | 'none';
			};
		}
	}
}

export {};
