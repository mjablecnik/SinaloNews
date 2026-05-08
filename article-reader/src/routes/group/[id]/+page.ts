import type { PageLoad } from './$types';
import { getGroupDetail } from '$lib/api';
import type { GroupDetail } from '$lib/types';

export const load: PageLoad = async ({ params }) => {
	const id = parseInt(params.id, 10);
	if (isNaN(id)) {
		return { group: null as GroupDetail | null, error: 'Invalid group ID' };
	}
	try {
		const group = await getGroupDetail(id);
		return { group, error: null };
	} catch (e) {
		const error = e instanceof Error ? e.message : 'Failed to load group';
		return { group: null as GroupDetail | null, error };
	}
};
