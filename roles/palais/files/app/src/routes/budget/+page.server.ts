import type { PageServerLoad } from './$types';

// Data fetched client-side via /api/v1/budget for live updates
export const load: PageServerLoad = async () => {
	return {};
};
