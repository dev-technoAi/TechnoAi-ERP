from datetime import timedelta

import pytz

from odoo import api, fields, models


class TaskhubReport(models.AbstractModel):
    """ Figures for the Reports page: commercial pipeline, tasks and team workload. """
    _name = 'taskhub.report'
    _description = 'Task Hub reports'

    @api.model
    def get_report(self, days=30):
        days = 90 if int(days) == 90 else 30
        now = fields.Datetime.now()
        start = now - timedelta(days=days)
        prev_start = start - timedelta(days=days)
        Rfq = self.env['taskhub.rfq']
        Task = self.env['taskhub.task']
        currency = self.env.company.currency_id

        won = Rfq.search([('state', '=', 'won'), ('date_closed', '>=', start)])
        won_prev = Rfq.search([('state', '=', 'won'), ('date_closed', '>=', prev_start), ('date_closed', '<', start)])
        inbound = Rfq.search_count([('date_received', '>=', start)])
        inbound_week = Rfq.search_count([('date_received', '>=', now - timedelta(days=7))])
        open_rfqs = Rfq.search([('is_open', '=', True)])
        closed = Rfq.search_count([('state', 'in', ('won', 'lost')), ('date_closed', '>=', start)])

        done = Task.search([('state', '=', 'done'), ('date_done', '>=', start)])
        on_time = done.filtered(lambda t: not t.date_deadline or t.date_done <= t.date_deadline)

        quotes = self.env['taskhub.quotation'].search([('rfq_id', 'in', won.ids), ('amount_untaxed', '>', 0)])
        if not quotes:
            quotes = self.env['taskhub.quotation'].search([('state', '=', 'sent'), ('date', '>=', start.date()), ('amount_untaxed', '>', 0)])
        untaxed = sum(quotes.mapped('amount_untaxed'))
        margin = (untaxed - sum(quotes.mapped('amount_cost'))) / untaxed * 100 if untaxed else 0.0

        won_total = sum(won.mapped('amount'))
        won_prev_total = sum(won_prev.mapped('amount'))
        return {
            'days': days,
            'currency': {'symbol': currency.symbol, 'position': currency.position, 'name': currency.name},
            'kpis': {
                'won_revenue': won_total,
                'won_change': round((won_total - won_prev_total) / won_prev_total * 100) if won_prev_total else None,
                'inbound_rfqs': inbound,
                'inbound_week': inbound_week,
                'tasks_done': len(done),
                'on_time_percent': round(len(on_time) / len(done) * 100) if done else None,
                'avg_deal': won_total / len(won) if won else 0.0,
                'active_pipeline': sum(open_rfqs.mapped('amount')),
                'open_rfqs': len(open_rfqs),
                'win_rate': round(len(won) / closed * 100) if closed else None,
                'gross_margin': round(margin, 1),
            },
            'revenue': self._daily_revenue(won | won_prev, start, days),
            'workload': self._workload(),
        }

    def _daily_revenue(self, won, start, days):
        """ Won value per day of the period, next to the same day of the previous period. """
        tz = pytz.timezone(self.env.user.tz or 'UTC')

        def local_date(dt):
            return pytz.utc.localize(dt).astimezone(tz).date()

        start_day = local_date(start)
        current, previous = {}, {}
        for rfq in won:
            day = local_date(rfq.date_closed)
            offset = (day - start_day).days
            bucket = current if offset >= 0 else previous
            key = offset if offset >= 0 else offset + days
            bucket[key] = bucket.get(key, 0.0) + rfq.amount
        return [{
            'label': (start_day + timedelta(days=i)).strftime('%b %d'),
            'value': current.get(i, 0.0),
            'previous': previous.get(i, 0.0),
        } for i in range(days + 1)]

    def _workload(self):
        groups = self.env['taskhub.task']._read_group(
            [('state', '!=', 'done'), ('user_id', '!=', False)], ['user_id'], ['__count'])
        employees = {e.user_id.id: e for e in self.env['hr.employee'].search([('user_id', 'in', [g[0].id for g in groups])])}
        rows = [{
            'user_id': user.id,
            'name': user.name,
            'department': employees.get(user.id) and employees[user.id].department_id.name or '',
            'open_tasks': count,
        } for user, count in groups]
        return sorted(rows, key=lambda r: -r['open_tasks'])
