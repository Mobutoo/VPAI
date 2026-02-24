declare global {
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
