import { db } from '$lib/server/db';
import { deployments, deploymentSteps } from '$lib/server/db/schema';
import { eq, and } from 'drizzle-orm';
import { ok, err } from '$lib/server/api/response';
import type { RequestHandler } from './$types';

type StepStatus = 'running' | 'success' | 'failed';

interface CallbackBody {
	deploymentId: number;
	stepName: string;
	status: StepStatus;
	output?: string;
	error?: string;
}

export const POST: RequestHandler = async ({ request }) => {
	try {
		const body = await request.json() as CallbackBody;

		const { deploymentId, stepName, status } = body;

		if (!deploymentId || !stepName || !status) {
			return err('Missing required fields: deploymentId, stepName, status', 400);
		}

		if (!['running', 'success', 'failed'].includes(status)) {
			return err('Invalid status value', 400);
		}

		const now = new Date();

		// Check if step already exists for this deployment + stepName
		const [existingStep] = await db
			.select()
			.from(deploymentSteps)
			.where(
				and(
					eq(deploymentSteps.deploymentId, deploymentId),
					eq(deploymentSteps.stepName, stepName)
				)
			);

		if (existingStep) {
			await db
				.update(deploymentSteps)
				.set({
					status,
					output: body.output ?? existingStep.output,
					error: body.error ?? existingStep.error,
					...(status !== 'running' ? { completedAt: now } : {}),
					...(status === 'running' && !existingStep.startedAt ? { startedAt: now } : {})
				})
				.where(eq(deploymentSteps.id, existingStep.id));
		} else {
			// Determine position from count of existing steps
			const existingSteps = await db
				.select({ id: deploymentSteps.id })
				.from(deploymentSteps)
				.where(eq(deploymentSteps.deploymentId, deploymentId));

			const position = existingSteps.length;

			await db.insert(deploymentSteps).values({
				deploymentId,
				stepName,
				status,
				position,
				startedAt: status === 'running' ? now : null,
				completedAt: status !== 'running' ? now : null,
				output: body.output ?? null,
				error: body.error ?? null
			});
		}

		// Update parent deployment if step is terminal
		if (status === 'failed') {
			await db
				.update(deployments)
				.set({
					status: 'failed',
					errorSummary: body.error ?? `Step "${stepName}" failed`
				})
				.where(eq(deployments.id, deploymentId));
		} else if (status === 'success') {
			// Check if all steps for this deployment are successful
			const allSteps = await db
				.select({ status: deploymentSteps.status })
				.from(deploymentSteps)
				.where(eq(deploymentSteps.deploymentId, deploymentId));

			const allSucceeded = allSteps.length > 0 && allSteps.every((s) => s.status === 'success');

			if (allSucceeded) {
				await db
					.update(deployments)
					.set({ status: 'success', completedAt: now })
					.where(eq(deployments.id, deploymentId));
			}
		}

		return ok({ received: true });
	} catch (e) {
		return err(e instanceof Error ? e.message : 'Unknown error');
	}
};
