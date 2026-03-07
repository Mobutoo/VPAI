import type { RequestHandler } from '@sveltejs/kit';
import { ok, err } from '$lib/server/api/response';
import { recordCost } from '$lib/server/costs/aggregator';
import * as ovh from '$lib/server/providers/ovh';
import * as hetzner from '$lib/server/providers/hetzner';
import { env } from '$env/dynamic/private';

/** Sync costs from OVH invoices + Hetzner estimated pricing */
export const POST: RequestHandler = async () => {
    try {
        let recorded = 0;
        const errors: { source: string; error: string }[] = [];

        const now = new Date();
        const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
        const monthEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59);

        // ── OVH: import recent invoices ──────────────────────────────────
        if (env.OVH_APPLICATION_KEY && env.OVH_APPLICATION_SECRET && env.OVH_CONSUMER_KEY) {
            try {
                const invoices = await ovh.getRecentInvoices(10);

                for (const inv of invoices) {
                    try {
                        const invDate = new Date(inv.date);
                        const invMonthEnd = new Date(invDate.getFullYear(), invDate.getMonth() + 1, 0, 23, 59, 59);

                        await recordCost(
                            'ovh',
                            'invoice',
                            inv.priceWithTax.value,
                            invDate,
                            invMonthEnd,
                            undefined,
                            `OVH Invoice ${inv.invoiceId}`,
                            {
                                invoiceId: inv.invoiceId,
                                currency: inv.priceWithTax.currencyCode,
                                url: inv.url
                            }
                        );
                        recorded++;
                    } catch (e) {
                        errors.push({
                            source: 'ovh',
                            error: e instanceof Error ? e.message : 'Unknown error'
                        });
                    }
                }
            } catch (e) {
                errors.push({
                    source: 'ovh',
                    error: e instanceof Error ? e.message : 'OVH billing API error'
                });
            }
        }

        // ── Hetzner: estimate monthly costs from server types ────────────
        const hetznerTokens = hetzner.getTokens();
        if (hetznerTokens.length > 0) {
            try {
                const estimate = await hetzner.getUpcomingInvoice();

                if (estimate.amount > 0) {
                    await recordCost(
                        'hetzner',
                        'estimate',
                        estimate.amount,
                        monthStart,
                        monthEnd,
                        undefined,
                        `Hetzner monthly estimate (${now.toISOString().slice(0, 7)})`,
                        { currency: estimate.currency, source: 'pricing_table' }
                    );
                    recorded++;
                }
            } catch (e) {
                errors.push({
                    source: 'hetzner',
                    error: e instanceof Error ? e.message : 'Hetzner cost estimate error'
                });
            }
        }

        return ok({ recorded, errors });
    } catch (e) {
        return err(e instanceof Error ? e.message : 'Unknown error');
    }
};
