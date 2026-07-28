# -*- coding: utf-8 -*-
#################################################################################
# Author      : Zero For Information Systems (<www.erpzero.com>)
# Copyright(c): 2016-Zero For Information Systems
# All Rights Reserved.
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################

from collections import defaultdict
from datetime import timedelta
from itertools import groupby

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import (
    AccessError,
    RedirectWarning,
    UserError,
    ValidationError,
)
from odoo.fields import Command
from odoo.http import request
from odoo.osv import expression
from odoo.tools import (
    float_round,
    float_is_zero,
    format_amount,
    format_date,
    is_html_empty,
    SQL,
)
from odoo.tools.mail import html_keep_url


class AccountMove(models.Model):
    _inherit = 'account.move'

    def write(self, vals):
        # Capture opportunities BEFORE write for cases where opportunity_id is being changed/removed
        old_opportunities = self.mapped('opportunity_id')

        res = super().write(vals)

        # Capture opportunities AFTER write
        new_opportunities = self.mapped('opportunity_id')

        # Combine both to cover reassignment cases
        all_opportunities = (old_opportunities | new_opportunities).filtered('id')

        if all_opportunities and (
                'opportunity_id' in vals
                or 'sale_id' in vals
                or 'state' in vals  # posted/draft/cancelled changes
                or 'invoice_line_ids' in vals  # line amount changes
                or 'payment_state' in vals  # paid status changes
        ):
            all_opportunities._compute_fulfillment_status()
            # Also recompute legacy invoice count on related SOs
            sos = all_opportunities.mapped('order_ids').filtered(lambda s: s.is_legacy)
            sos._compute_legacy_invoice_count()

        return res

class ProductAttributeCustomValue(models.Model):
    _inherit = "product.attribute.custom.value"

    crm_lead_line_id = fields.Many2one('crm.lead.product', string="Work Items", required=True, ondelete='cascade')

    @api.constrains('crm_lead_line_id')
    def _check_crm_lead_line_id_unicity(self):
        for record in self:
            if record.crm_lead_line_id and self.env['product.attribute.custom.value'].search_count([('crm_lead_line_id', '=', record.crm_lead_line_id.id)]) > 1:
                raise ValidationError(_('Only one Custom Value is allowed per Attribute Value per Work Items.'))

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_view_legacy_invoices(self):
        self.ensure_one()
        invoices = self.env['account.move'].search([
            ('sale_id', '=', self.id),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
        ])
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        if len(invoices) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = invoices.id
        else:
            action['domain'] = [('id', 'in', invoices.ids)]
        return action

    legacy_invoice_count = fields.Integer(
        string="Legacy Invoice Count",
        compute='_compute_legacy_invoice_count',
    )

    # @api.depends('opportunity_id')
    def _compute_legacy_invoice_count(self):
        for order in self:
            if order.opportunity_id and order.is_legacy:
                order.legacy_invoice_count = self.env['account.move'].search_count([
                    ('sale_id', '=', order.id),
                    ('move_type', 'in', ['out_invoice', 'out_refund']),
                ])
            else:
                order.legacy_invoice_count = 0

    def write(self, vals):
        old_opportunities = self.mapped('opportunity_id')
        res = super().write(vals)
        if 'opportunity_id' in vals:
            new_opportunities = self.mapped('opportunity_id')
            (old_opportunities | new_opportunities)._compute_fulfillment_status()
        return res

    from_opportunity = fields.Boolean("From Opportunity")

    @api.onchange('opportunity_id')
    def opportunity_id_change(self):
        opportunity_id = self.opportunity_id.with_context(lang=self.partner_id.lang)
        for order in self:
            if opportunity_id:
                order.update_from_opportunity()


        
    def update_from_opportunity(self):
        for order in self:
            opportunity_id = order.opportunity_id
            if not opportunity_id:
                return
            sequence = 10
            order.sudo().update({
                'opportunity_id': opportunity_id.id,
                'from_opportunity': True,
                'company_id': self.env.company or self.company_id.id,
                'partner_id': opportunity_id.partner_id.id,
                'campaign_id': opportunity_id.campaign_id.id,
                'medium_id': opportunity_id.medium_id.id,
                'origin': opportunity_id.name,
                'order_line': [],
                'source_id': opportunity_id.source_id.id,
                'tag_ids': [(6, 0, opportunity_id.tag_ids.ids)],
                'payment_term_id' : opportunity_id.payment_term_id.id or False,
                'partner_shipping_id' : opportunity_id.partner_shipping_id.id or False,
                'pricelist_id' : opportunity_id.pricelist_id.id or False,
                'currency_id' : opportunity_id.currency_id.id,
                'fiscal_position_id' : opportunity_id.fiscal_position_id.id or False,
                'note' : opportunity_id.note or False,
                'sale_order_template_id': opportunity_id.quotation_template_id.id or False,
                'plan_id': opportunity_id.plan_id.id or False,
                'partner_invoice_id':opportunity_id.partner_invoice_id.id or False,

               })

            lead_lines_data = [fields.Command.clear()]

            lead_lines_data += [
                fields.Command.create(line.crm_led_products())
                for line in opportunity_id.lead_line
            ]

            order.order_line = lead_lines_data
            # self.env.cr.commit()

            price_map = {
                line.id: line.price_unit
                for line in opportunity_id.lead_line
                if not line.display_type
            }
            for sol in order.order_line.filtered(lambda l: l.lead_id and not l.display_type):
                of_price = price_map.get(sol.lead_id.id)
                if of_price is not None:
                    sol.price_unit = of_price
                    sol.technical_price_unit = of_price

    @api.onchange('sale_order_template_id')
    def _onchange_sale_order_template_id(self):
        if self.from_opportunity and self.opportunity_id and self.opportunity_id.lead_line:
            return  # Do nothing — skip template line creation
        return super()._onchange_sale_order_template_id()

    @api.onchange('plan_id')
    def _onchange_plan_id_recompute_prices(self):
        """Safe version - only invalidate rule, let computes run normally"""
        if not self.order_line:
            return
        self.sudo()._recompute_prices()



class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    lead_id = fields.Many2one('crm.lead.product', 'Opportunity Line', ondelete='set null', index='btree_not_null')
    opportunity_id = fields.Many2one('crm.lead', 'Opportunity', related='order_id.opportunity_id', readonly=True)


    @api.depends('product_id', 'product_uom_id', 'product_uom_qty')
    def _compute_price_unit(self):
        for line in self:
            if line.lead_id and not self.env.context.get('force_price_recompute'):
                of_line = line.lead_id  # crm.lead.product record
                if of_line and of_line.price_unit:
                    line.price_unit = of_line.price_unit
                    continue
            super(SaleOrderLine, line)._compute_price_unit()


class CrmLead(models.Model):
    _inherit = ['crm.lead']

    def _get_lang(self):
        self.ensure_one()

        if self.partner_id.lang and not self.partner_id.is_public:
            return self.partner_id.lang

        return self.env.lang
        
    lead_line = fields.One2many('crm.lead.product', 'lead_id', string='Work Items', copy=True)
    ordered = fields.Boolean(string="Converted to Quotation",compute='ordered_state',store=True)
    company_price_include = fields.Selection(related='company_id.account_price_include')

    sale_warning_text = fields.Text(
        "Sale Warning",
        help="Internal warning for the partner or the products as set by the user.",
        compute='_compute_sale_warning_text')

    partner_id = fields.Many2one(
        'res.partner', string='Customer', check_company=True, index=True, tracking=10,
        help="Linked partner (optional). Usually created when converting the lead. You can find a partner by its Name, TIN, Email or Internal Reference.")

    def action_quotations_order_line(self):
        order_line = self.env['sale.order.line']
        order_line = [fields.Command.clear()]
        order_line += [
            fields.Command.create(line.crm_led_products())
            for line in self.lead_line
        ]
        return order_line

    def action_new_quotation(self):
        action = super().action_new_quotation()
        action['context']['default_order_line'] = self.action_quotations_order_line() or []
        return action

    def _get_lang(self):
        self.ensure_one()

        if self.partner_id.lang and not self.partner_id.is_public:
            return self.partner_id.lang

        return self.env.lang
  
    
    def action_open_discount_wizard(self):
        self.ensure_one()
        return {
            'name': _("Discount"),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.discount',
            'view_mode': 'form',
            'target': 'new',
        }
    @api.depends('quotation_count')
    def ordered_state(self):
        for rec in self:
            if rec.quotation_count and rec.quotation_count >0:
                rec.ordered = True

    note = fields.Html(
        string="Terms and conditions",
        compute='_compute_note',
        store=True, readonly=False, precompute=True)

    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string="Fiscal Position",
        compute='_compute_fiscal_position_id',
        store=True, readonly=False, precompute=True, check_company=True,
        help="Fiscal positions are used to adapt taxes and accounts for particular customers or sales orders/invoices."
            "The default value comes from the customer.",
        domain="[('company_id', '=', company_id)]")
    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string="Pricelist",
        compute='_compute_pricelist_id',
        store=True, readonly=False, precompute=True, check_company=True,
        tracking=1,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="If you change the pricelist, only newly added lines will be affected.")
    payment_term_id = fields.Many2one(
        comodel_name='account.payment.term',
        string="Payment Terms",
        compute='_compute_payment_term_id',
        store=True, readonly=False, precompute=True, check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency_id',
        store=True,
        precompute=True,
        ondelete='restrict'
    )
    company_currency_id = fields.Many2one(
        string='Company Currency',
        related='company_id.currency_id', readonly=True, store=True,)
    currency_rate = fields.Float(
        string="Currency Rate",
        compute='_compute_currency_rate',
        digits=(12, 6),
        precompute=True)

    partner_invoice_id = fields.Many2one(
        comodel_name='res.partner',
        string="Bill To",
        compute='_compute_partner_invoice_id',
        store=True, readonly=False, required=False, precompute=True,
        check_company=True,
        index='btree_not_null')
    partner_shipping_id = fields.Many2one(
        comodel_name='res.partner',
        string="Ship To",
        compute='_compute_partner_shipping_id',
        store=True, readonly=False, required=False, precompute=True,
        check_company=True,
        index='btree_not_null')

    terms_type = fields.Selection(related='company_id.terms_type')

    # ─── Fulfillment Status Fields ────────────────────────────────────────────

    total_of_value = fields.Monetary(
        string="Total OF Value",
        compute='_compute_fulfillment_status',
        store=True,
        currency_field='company_currency_id',
        help="Sum of all Order Form product line subtotals (pre-tax).",
    )
    total_invoiced = fields.Monetary(
        string="Total Invoiced to Date",
        compute='_compute_fulfillment_status',
        store=True,
        currency_field='company_currency_id',
        help="Sum of amount_untaxed across all posted/confirmed invoices linked to this Order Form.",
    )
    percent_invoiced = fields.Float(
        string="% Invoiced",
        compute='_compute_fulfillment_status',
        store=True,
        digits=(16, 2),
        help="(Total Invoiced to Date / Total OF Value) × 100",
    )
    remaining_to_invoice = fields.Monetary(
        string="Remaining to Invoice",
        compute='_compute_fulfillment_status',
        store=True,
        currency_field='company_currency_id',
        help="Total OF Value minus Total Invoiced to Date.",
    )
    percent_remaining = fields.Float(
        string="% Remaining",
        compute='_compute_fulfillment_status',
        store=True,
        digits=(16, 2),
        help="(Remaining to Invoice / Total OF Value) × 100",
    )

    @api.depends(
        'order_ids',  # ← add this
        'order_ids.is_legacy',
        'order_ids.invoice_ids',  # ← add this
        'order_ids.legacy_invoice_count',  # ← this
        'lead_line.price_subtotal',
        'order_ids.invoice_ids.amount_untaxed',
        'order_ids.invoice_ids.state',
        'order_ids.invoice_ids.move_type',
    )
    def _compute_fulfillment_status(self):
        for lead in self:
            # ── Total OF Value ──
            of_value = sum(lead.lead_line.filtered(
                lambda l: not l.display_type
            ).mapped('price_subtotal'))

            invoiced = 0.0

            # ── Split: legacy SOs vs normal SOs ──
            legacy_sos = lead.order_ids.filtered(lambda s: s.is_legacy)
            normal_sos = lead.order_ids.filtered(lambda s: not s.is_legacy)

            # Normal SOs: use standard invoice linkage
            normal_invoices = normal_sos.mapped('invoice_ids').filtered(
                lambda inv: inv.state == 'posted' and inv.move_type in ('out_invoice', 'out_refund')
            )
            invoiced += sum(
                inv.amount_untaxed if inv.move_type == 'out_invoice' else -inv.amount_untaxed
                for inv in normal_invoices
            )

            # Legacy SOs: collect invoices via opportunity_id on account.move
            if legacy_sos:
                legacy_invoices = self.env['account.move'].search([
                    ('opportunity_id', '=', lead.id),
                    ('state', '=', 'posted'),
                    ('move_type', 'in', ['out_invoice', 'out_refund']),
                    # Exclude any already counted via normal SO linkage
                    ('id', 'not in', normal_invoices.ids),
                ])
                invoiced += sum(
                    inv.amount_untaxed if inv.move_type == 'out_invoice' else -inv.amount_untaxed
                    for inv in legacy_invoices
                )

            remaining = of_value - invoiced
            lead.total_of_value = of_value
            lead.total_invoiced = invoiced
            lead.remaining_to_invoice = remaining
            lead.percent_invoiced = (invoiced / of_value * 100.0) if of_value else 0.0
            lead.percent_remaining = (remaining / of_value * 100.0) if of_value else 0.0

    # ─── End Fulfillment Status Fields ───────────────────────────────────────
    @api.depends('partner_id')
    def _compute_note(self):
        use_invoice_terms = self.env['ir.config_parameter'].sudo().get_param('account.use_invoice_terms')
        if not use_invoice_terms:
            return
        for order in self:
            order = order.with_company(order.company_id)
            if order.terms_type == 'html' and self.env.company.invoice_terms_html:
                baseurl = html_keep_url(order._get_note_url() + '/terms')
                context = {'lang': order.partner_id.lang or self.env.user.lang}
                order.note = _('Terms & Conditions: %s', baseurl)
                del context
            elif not is_html_empty(self.env.company.invoice_terms):
                if order.partner_id.lang:
                    order = order.with_context(lang=order.partner_id.lang)
                order.note = order.env.company.invoice_terms


    @api.model
    def _get_note_url(self):
        return self.env.company.get_base_url()

    @api.depends('partner_id')
    def _compute_partner_shipping_id(self):
        for order in self:
            order.partner_shipping_id = order.partner_id.address_get(['delivery'])[
                'delivery'] if order.partner_id else False
    @api.depends('partner_id')
    def _compute_partner_invoice_id(self):
        for order in self:
            order.partner_invoice_id = order.partner_id.address_get(['invoice'])['invoice'] if order.partner_id else False

    @api.depends('partner_shipping_id', 'partner_id', 'company_id')
    def _compute_fiscal_position_id(self):
        cache = {}
        for order in self:
            if not order.partner_id:
                order.fiscal_position_id = False
                continue
            fpos_id_before = order.fiscal_position_id.id
            key = (order.company_id.id, order.partner_id.id, order.partner_shipping_id.id)
            if key not in cache:
                cache[key] = self.env['account.fiscal.position'].with_company(
                    order.company_id
                )._get_fiscal_position(order.partner_id, order.partner_shipping_id).id
            if fpos_id_before != cache[key] and order.lead_line:
                order.show_update_fpos = True
            order.fiscal_position_id = cache[key]

    amount_untaxed = fields.Monetary(string="Untaxed Amount", store=True, compute='_compute_amounts', tracking=5)
    amount_tax = fields.Monetary(string="Taxes", store=True, compute='_compute_amounts')
    amount_total = fields.Monetary(string="Total", store=True, compute='_compute_amounts', tracking=4)

    amount_undiscounted = fields.Float(
        string="Amount Before Discount",
        compute='_compute_amount_undiscounted', digits=0)
    country_code = fields.Char(related='company_id.account_fiscal_country_id.code', string="Country code")
    tax_calculation_rounding_method = fields.Selection(
        related='company_id.tax_calculation_rounding_method',
        depends=['company_id'])
    tax_country_id = fields.Many2one(
        comodel_name='res.country',
        compute='_compute_tax_country_id',
        compute_sudo=True)
    tax_totals = fields.Binary(compute='_compute_tax_totals', exportable=False)

    @api.depends('company_id', 'fiscal_position_id')
    def _compute_tax_country_id(self):
        for record in self:
            if record.fiscal_position_id.foreign_vat:
                record.tax_country_id = record.fiscal_position_id.country_id
            else:
                record.tax_country_id = record.company_id.account_fiscal_country_id


    show_update_fpos = fields.Boolean(
        string="Has Fiscal Position Changed", store=False)
    show_update_pricelist = fields.Boolean(
        string="Has Pricelist Changed", store=False)

   
    def _compute_amount_undiscounted(self):
        for order in self:
            total = 0.0
            for line in order.lead_line:
                total += (line.price_subtotal * 100)/(100-line.discount) if line.discount != 100 else (line.price_unit * line.product_uom_qty)
            order.amount_undiscounted = total


    @api.depends('lead_line.price_subtotal', 'currency_id', 'company_id')
    def _compute_amounts(self):
        AccountTax = self.env['account.tax']
        for order in self:
            order_lines = order.lead_line.filtered(lambda x: not x.display_type)
            base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
            AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
            tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=order.currency_id or order.company_currency_id,
                company=order.company_id,
            )
            order.amount_untaxed = tax_totals['base_amount_currency']
            order.amount_tax = tax_totals['tax_amount_currency']
            order.amount_total = tax_totals['total_amount_currency']
            if order.amount_untaxed:
                ammount_untax_company_cuurency = order.amount_untaxed * order.currency_rate
                order.write({'expected_revenue':ammount_untax_company_cuurency})

    @api.depends('partner_id')
    def _compute_payment_term_id(self):
        for order in self:
            order = order.with_company(order.company_id)
            order.payment_term_id = order.partner_id.property_payment_term_id

    @api.depends('partner_id', 'company_id')
    def _compute_pricelist_id(self):
        for order in self:
            if not order.partner_id:
                order.pricelist_id = self.env['product.pricelist'].search([
                    '|', ('company_id', '=', False),
                    ('company_id', '=', self.env.company.id)], limit=1)
            else:
                order = order.with_company(order.company_id)
                order.pricelist_id = order.partner_id.property_product_pricelist

    @api.depends('pricelist_id', 'company_id')
    def _compute_currency_id(self):
        for order in self:
            order.currency_id = order.pricelist_id.currency_id or order.company_currency_id

    @api.depends('currency_id', 'date_last_stage_update', 'company_id')
    def _compute_currency_rate(self):
        for order in self:
            order_date = order and order.date_last_stage_update.date()
            # date = order_date or fields.Date.today()
            date = order_date or fields.Datetime.now
            order.currency_rate = self.env['res.currency']._get_conversion_rate(
                from_currency=order.company_currency_id,
                to_currency=order.currency_id,
                company=order.company_id,
                date=date,
            )
  

    @api.depends_context('lang')
    @api.depends('lead_line.price_subtotal', 'currency_id', 'company_id')
    def _compute_tax_totals(self):
        AccountTax = self.env['account.tax']
        for order in self:
            order_lines = order.lead_line.filtered(lambda x: not x.display_type)
            base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
            AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
            order.tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=order.currency_id or order.company_currency_id,
                company=order.company_id,
            )
   

    @api.constrains('company_id', 'lead_line')
    def _check_lead_line_company_id(self):
        for order in self:
            companies = order.lead_line.product_id.company_id
            if companies and companies != order.company_id:
                bad_products = order.lead_line.product_id.filtered(lambda p: p.company_id and p.company_id != order.company_id)
                raise ValidationError(_(
                    "Your opportunity contains products from company %(product_company)s whereas your opportunity belongs to company %(quote_company)s. \n Please change the company of your opportunity or remove the products from other companies (%(bad_products)s).",
                    product_company=', '.join(companies.mapped('display_name')),
                    quote_company=order.company_id.display_name,
                    bad_products=', '.join(bad_products.mapped('display_name')),
                ))


    @api.onchange('fiscal_position_id')
    def _onchange_fpos_id_show_update_fpos(self):
        if self.lead_line and (
            not self.fiscal_position_id
            or (self.fiscal_position_id and self._origin.fiscal_position_id != self.fiscal_position_id)
        ):
            self.show_update_fpos = True


    @api.depends('partner_id.name', 'partner_id.sale_warn_msg', 'lead_line.sale_line_warn_msg')
    def _compute_sale_warning_text(self):
        for order in self:
            warnings = OrderedSet()
            if partner_msg := order.partner_id.sale_warn_msg:
                warnings.add((order.partner_id.name or order.partner_id.display_name) + ' - ' + partner_msg)
            for line in order.lead_line:
                if product_msg := line.sale_line_warn_msg:
                    warnings.add(line.product_id.display_name + ' - ' + product_msg)
            order.sale_warning_text = '\n'.join(warnings)

            
    @api.onchange('pricelist_id')
    def _onchange_pricelist_id_show_update_prices(self):
        if self and self.pricelist_id and self._origin.pricelist_id != self.pricelist_id:
            self.show_update_pricelist = True


    def _merge_get_fields_specific(self):
        fields_info = super()._merge_get_fields_specific()
        fields_info['lead_line'] = lambda fname, leads: [(4, order.id) for order in leads.lead_line]
        return fields_info

    def action_update_taxes(self):
        self.ensure_one()

        self._recompute_taxes()

        if self.partner_id:
            self.message_post(body=_("Product taxes have been recomputed according to fiscal position %s.",
                self.fiscal_position_id._get_html_link() if self.fiscal_position_id else "")
            )

    def _recompute_taxes(self):
        lines_to_recompute = self.lead_line.filtered(lambda line: not line.display_type)
        lines_to_recompute._compute_tax_id()
        self.show_update_fpos = False

    def action_update_prices(self):
        self.ensure_one()

        self._recompute_prices()

        if self.pricelist_id:
            self.message_post(body=_(
                "Product prices have been recomputed according to pricelist %s.",
                self.pricelist_id._get_html_link(),
            ))


    def _get_update_prices_lines(self):
        return self.lead_line.filtered(lambda line: not line.display_type)

    def _recompute_prices(self):
        lines_to_recompute = self._get_update_prices_lines()
        lines_to_recompute.invalidate_recordset(['pricelist_item_id'])
        lines_to_recompute.technical_price_unit = 0.0
        lines_to_recompute._compute_price_unit()
        lines_to_recompute.discount = 0.0
        lines_to_recompute._compute_discount()
        self.show_update_pricelist = False

    @api.onchange('plan_id')
    def _onchange_plan_id(self):
        if self.lead_line:
            self.lead_line._recompute_prices_on_plan_change()
            # Optional: show a message like in sale order
            self.show_update_pricelist = True  # if you have this field

    # Also call it when pricelist changes (you already have some onchange)
    @api.onchange('pricelist_id')
    def _onchange_pricelist_id(self):
        if self.lead_line:
            self.lead_line._recompute_prices_on_plan_change()
class CrmLeadProduct(models.Model):
    _name = 'crm.lead.product'
    _inherit = 'analytic.mixin'
    _description = 'Work Items'
    _rec_names_search = ['name', 'lead_id.name']
    _order = 'lead_id, sequence, id'
    _check_company_auto = True

    # def _get_grouped_section_summary(self, display_taxes=True):
    #     """Return a tax-wise summary of sales order lines linked to section.
    #
    #     Group lines by their tax IDs and computes subtotal and total for each group.
    #     """
    #     self.ensure_one()
    #
    #     section_lines = self.lead_id.lead_line.filtered(self.display_type == 'line_section')
    #
    #     if display_taxes:
    #         res = [
    #             {
    #                 'tax_labels': [],
    #                 'price_subtotal': sum(lines.mapped('price_subtotal')),
    #                 'price_total': sum(lines.mapped('price_total')),
    #             }
    #             for taxes, lines in section_lines.grouped('tax_id').items()
    #         ]
    #     else:
    #         res = [{
    #             'tax_labels': [],
    #             'price_subtotal': sum(section_lines.mapped('price_subtotal')),
    #             'price_total': sum(section_lines.mapped('price_total')),
    #         }]
    #     return res or [{
    #         'tax_labels': [],
    #         'price_subtotal': 0.0,
    #         'price_total': 0.0,
    #     }]


    def _has_taxes(self):
        """Check if a line has taxes or not. For (sub)sections, check if any child line has taxes."""
        self.ensure_one()
        return bool(
            self.tax_id
            or (self.display_type and any(line._has_taxes() for line in self._get_section_lines())),
        )

    def crm_led_products(self, order=False):
        self.ensure_one()
        aml_currency = order and order.currency_id or self.currency_id
        order_date = order and order.date_last_stage_update.date()
        date = order_date or fields.Date.today()
        res = {
            'sequence': self.sequence,
            'display_type': self.display_type,
            'name': self.name,
            'product_id': self.product_id.id,
            'product_uom_qty': self.product_uom_qty,
            'product_uom_id': self.product_uom.id,
            'price_unit': self.currency_id._convert(self.price_unit, aml_currency, self.company_id, date, round=False),
            # 'tax_ids': [(6, 0, self.tax_id.ids)],
            'product_type': self.product_type,
            'customer_lead': self.customer_lead,
            'discount': self.discount,
            'lead_id': self.id,

        }
        return res


    sale_lead_lines = fields.One2many('sale.order.line', 'lead_id', string="Sales Lines", readonly=True, copy=False)
    ordered = fields.Boolean(string="Converted to Quotation",related='lead_id.ordered',store=True)
    lead_id = fields.Many2one(
        comodel_name='crm.lead',
        string="Opportunity Reference",
        required=True, ondelete='cascade', index=True, copy=False)

    # subscription_plan_id = fields.Many2one('sale.subscription.plan',related="lead_id.plan_id", string="Subscription Term")
    sequence = fields.Integer(string="Sequence", default=10)
    state = fields.Many2one(
        related='lead_id.stage_id',
        string="Order Stage",
        copy=False, store=True, precompute=True)
    company_id = fields.Many2one(
        related='lead_id.company_id',
        store=True, index=True, precompute=True)

    currency_id = fields.Many2one(
        related='lead_id.currency_id',
        depends=['lead_id.currency_id'],
        store=True, precompute=True)
    order_partner_id = fields.Many2one(
        related='lead_id.partner_id',
        string="Customer",
        store=True, index=True, precompute=True)
    salesman_id = fields.Many2one(
        related='lead_id.user_id',
        string="Salesperson",
        store=True, precompute=True)
    display_type = fields.Selection(
        selection=[
            ('line_section', "Section"),
            ('line_note', "Note"),
        ],
        default=False)
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Product",
        change_default=True, ondelete='restrict', check_company=True, index='btree_not_null',
        domain="[('sale_ok', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    product_template_id = fields.Many2one(
        string="Product Template",
        comodel_name='product.template',
        compute='_compute_product_template_id',
        readonly=False,
        search='_search_product_template_id',
        domain=[('sale_ok', '=', True)])
    product_custom_attribute_value_ids = fields.One2many(
        comodel_name='product.attribute.custom.value', inverse_name='crm_lead_line_id',
        string="Custom Values",
        compute='_compute_custom_attribute_values',
        store=True, readonly=False, precompute=True, copy=True)

    product_no_variant_attribute_value_ids = fields.Many2many(
        comodel_name='product.template.attribute.value',
        string="Extra Values",
        compute='_compute_no_variant_attribute_values',
        store=True, readonly=False, precompute=True, ondelete='restrict')
    name = fields.Text(
        string="Description",
        compute='_compute_name',
        store=True, readonly=False, required=True, precompute=True)
    product_uom_qty = fields.Float(
        string="Quantity",
        compute='_compute_product_uom_qty',
        digits='Product Unit', default=1.0,
        store=True, readonly=False, required=True, precompute=True)

    product_uom = fields.Many2one(
        comodel_name='uom.uom',
        string="Unit",
        compute='_compute_product_uom',
        domain='[("id", "in", allowed_uom_ids)]',
        store=True, readonly=False, precompute=True, ondelete='restrict')
    allowed_uom_ids = fields.Many2many('uom.uom', compute='_compute_allowed_uom_ids')
    is_product_archived = fields.Boolean(compute="_compute_is_product_archived")
    is_configurable_product = fields.Boolean(
        string="Is the product configurable?",
        related='product_template_id.has_configurable_attributes',
        depends=['product_id'])
    service_tracking = fields.Selection(related='product_id.service_tracking', depends=['product_id'])
    product_template_attribute_value_ids = fields.Many2many(
        related='product_id.product_template_attribute_value_ids',
        depends=['product_id'])
    product_custom_attribute_value_ids = fields.One2many(
        comodel_name='product.attribute.custom.value', inverse_name='sale_order_line_id',
        string="Custom Values",
        compute='_compute_custom_attribute_values',
        store=True, readonly=False, precompute=True, copy=True)
    product_no_variant_attribute_value_ids = fields.Many2many(
        comodel_name='product.template.attribute.value',
        string="Extra Values",
        compute='_compute_no_variant_attribute_values',
        store=True, readonly=False, precompute=True, ondelete='restrict')
    is_product_archived = fields.Boolean(compute="_compute_is_product_archived")


    @api.depends('product_id')
    def _compute_is_product_archived(self):
        for line in self:
            line.is_product_archived = line.product_id and not line.product_id.active
    tax_id = fields.Many2many(
        comodel_name='account.tax',
        string="Taxes",
        compute='_compute_tax_id',
        store=True, readonly=False, precompute=True,
        context={'active_test': False})
    pricelist_item_id = fields.Many2one(
        comodel_name='product.pricelist.item',
        compute='_compute_pricelist_item_id')
    price_unit = fields.Float(
        string="Unit Price",
        compute='_compute_price_unit',
        digits='Product Price',
        store=True, readonly=False, required=True, precompute=True)
    discount = fields.Float(
        string="Discount (%)",
        compute='_compute_discount',
        digits='Discount',
        store=True, readonly=False, precompute=True)
    price_reduce = fields.Float(
        string="Price Reduce",
        compute='_compute_price_reduce',
        digits='Product Price',
        store=True, precompute=True)
    technical_price_unit = fields.Float()
    price_subtotal = fields.Monetary(
        string="Subtotal",
        compute='_compute_amount',
        store=True, precompute=True)
    price_tax = fields.Float(
        string="Total Tax",
        compute='_compute_amount',
        store=True, precompute=True)
    price_total = fields.Monetary(
        string="Total",
        compute='_compute_amount',
        store=True, precompute=True)
    price_reduce_taxexcl = fields.Monetary(
        string="Price Reduce Tax excl",
        compute='_compute_price_reduce_taxexcl',
        store=True, precompute=True)
    price_reduce_taxinc = fields.Monetary(
        string="Price Reduce Tax incl",
        compute='_compute_price_reduce_taxinc',
        store=True, precompute=True)
    customer_lead = fields.Float(
        string="Lead Time",
        compute='_compute_customer_lead',
        store=True, readonly=False, required=True, precompute=True,
        help="Number of days between the order confirmation and the shipping of the products to the customer")
    product_type = fields.Selection(related='product_id.type', depends=['product_id'])
    tax_calculation_rounding_method = fields.Selection(
        related='company_id.tax_calculation_rounding_method',
        string='Tax calculation rounding method', readonly=True)
    sale_line_warn_msg = fields.Text(related='product_id.sale_line_warn_msg')
    translated_product_name = fields.Text(compute='_compute_translated_product_name')

    @api.depends('product_id')
    def _compute_translated_product_name(self):
        for line in self:
            line.translated_product_name = line.product_id.with_context(
                lang=line.lead_id._get_lang(),
            ).display_name
            
    @api.depends('product_id', 'product_id.uom_id', 'product_id.uom_ids')
    def _compute_allowed_uom_ids(self):
        for line in self:
            line.allowed_uom_ids = line.product_id.uom_id | line.product_id.uom_ids
            
    def _compute_customer_lead(self):
        self.customer_lead = 0.0

    @api.depends('product_id')
    def _compute_product_template_id(self):
        for line in self:
            line.product_template_id = line.product_id.product_tmpl_id

    def _search_product_template_id(self, operator, value):
        return [('product_id.product_tmpl_id', operator, value)]

    @api.depends('product_id')
    def _compute_custom_attribute_values(self):
        for line in self:
            if not line.product_id:
                line.product_custom_attribute_value_ids = False
                continue
            if not line.product_custom_attribute_value_ids:
                continue
            valid_values = line.product_id.product_tmpl_id.valid_product_template_attribute_line_ids.product_template_value_ids
            for pacv in line.product_custom_attribute_value_ids:
                if pacv.custom_product_template_attribute_value_id not in valid_values:
                    line.product_custom_attribute_value_ids -= pacv

    @api.depends('product_id')
    def _compute_no_variant_attribute_values(self):
        for line in self:
            if not line.product_id:
                line.product_no_variant_attribute_value_ids = False
                continue
            if not line.product_no_variant_attribute_value_ids:
                continue
            valid_values = line.product_id.product_tmpl_id.valid_product_template_attribute_line_ids.product_template_value_ids
            for ptav in line.product_no_variant_attribute_value_ids:
                if ptav._origin not in valid_values:
                    line.product_no_variant_attribute_value_ids -= ptav

    # @api.depends('product_id', 'linked_line_id', 'linked_line_ids')
    @api.depends('product_id')
    def _compute_name(self):
        for line in self:
            if not line.product_id:
                continue

            lang = line.lead_id._get_lang()
            if lang != self.env.lang:
                line = line.with_context(lang=lang)

            if line.product_id:
                line.name = line._get_sale_lead_line_multiline_description_sale()
                continue

    def _get_sale_lead_line_multiline_description_sale(self):
        self.ensure_one()
        description = (
            self.product_id.get_product_multiline_description_sale()
            + self._get_sale_lead_line_multiline_description_variants()
        )
        return description

    def _get_sale_lead_line_multiline_description_variants(self):
        no_variant_ptavs = self.product_no_variant_attribute_value_ids._origin.filtered(
            lambda ptav: ptav.display_type == 'multi' or ptav.attribute_line_id.value_count > 1
        )
        if not self.product_custom_attribute_value_ids and not no_variant_ptavs:
            return ""

        name = "\n"

        custom_ptavs = self.product_custom_attribute_value_ids.custom_product_template_attribute_value_id
        multi_ptavs = no_variant_ptavs.filtered(lambda ptav: ptav.display_type == 'multi').sorted()

        for ptav in (no_variant_ptavs - multi_ptavs - custom_ptavs):
            name += "\n" + ptav.display_name

        for pta, ptavs in groupby(multi_ptavs, lambda ptav: ptav.attribute_id):
            name += "\n" + _(
                "%(attribute)s: %(values)s",
                attribute=pta.name,
                values=", ".join(ptav.name for ptav in ptavs)
            )

        sorted_custom_ptav = self.product_custom_attribute_value_ids.custom_product_template_attribute_value_id.sorted()
        for patv in sorted_custom_ptav:
            pacv = self.product_custom_attribute_value_ids.filtered(lambda pcav: pcav.custom_product_template_attribute_value_id == patv)
            name += "\n" + pacv.display_name

        return name

    @api.depends('display_type', 'product_id')
    def _compute_product_uom_qty(self):
        for line in self:
            if line.display_type:
                line.product_uom_qty = 0.0

    @api.depends('product_id')
    def _compute_product_uom(self):
        for line in self:
            if not line.product_uom or (line.product_id.uom_id.id != line.product_uom.id):
                line.product_uom = line.product_id.uom_id


   
    @api.depends('product_id', 'company_id')
    def _compute_tax_id(self):
        taxes_by_product_company = defaultdict(lambda: self.env['account.tax'])
        lines_by_company = defaultdict(lambda: self.env['crm.lead.product'])
        cached_taxes = {}
        for line in self:
            lines_by_company[line.company_id] += line
        for product in self.product_id:
            for tax in product.taxes_id:
                taxes_by_product_company[(product, tax.company_id)] += tax
        for company, lines in lines_by_company.items():
            for line in lines.with_company(company):
                taxes, comp = None, company
                while not taxes and comp:
                    taxes = taxes_by_product_company[(line.product_id, comp)]
                    comp = comp.parent_id
                if not line.product_id or not taxes:
                    line.tax_id = False
                    continue
                fiscal_position = line.lead_id.fiscal_position_id
                cache_key = (fiscal_position.id, company.id, tuple(taxes.ids))
                cache_key += line._get_custom_compute_tax_cache_key()
                if cache_key in cached_taxes:
                    result = cached_taxes[cache_key]
                else:
                    result = fiscal_position.map_tax(taxes)
                    cached_taxes[cache_key] = result
                line.tax_id = result

    def _get_custom_compute_tax_cache_key(self):
        return tuple()

    @api.depends('product_id', 'product_uom', 'product_uom_qty')
    def _compute_pricelist_item_id(self):
        for line in self:
            order_date = line.lead_id.date_last_stage_update.date()
            date = order_date or fields.Date.today()
            if not line.product_id or line.display_type or not line.lead_id.pricelist_id:
                line.pricelist_item_id = False
            else:
                line.pricelist_item_id = line.lead_id.pricelist_id._get_product_rule(
                    line.product_id,
                    line.product_uom_qty or 1.0,
                    uom=line.product_uom,
                    date=date,
                    plan_id=line.lead_id.plan_id.id,
                )


    @api.depends('product_id', 'product_uom', 'product_uom_qty')
    def _compute_price_unit(self):
        for line in self:
            order_date = line.lead_id.date_last_stage_update.date()
            date = order_date or fields.Date.today()
            if not line.product_uom or not line.product_id:
                line.price_unit = 0.0
            else:
                # price = line.with_company(line.company_id)._get_display_price()
                price = line.with_company(line.company_id)._get_display_price_ignore_combo()
                line.price_unit = line.product_id._get_tax_included_unit_price(
                    line.company_id or line.env.company,
                    line.lead_id.currency_id,
                    date,
                    'sale',
                    fiscal_position=line.lead_id.fiscal_position_id,
                    product_price_unit=price,
                    product_currency=line.currency_id
                )

    def _recompute_prices_on_plan_change(self):
        """Helper to call from opportunity when plan_id changes"""
        lines_to_recompute = self.filtered(lambda l: not l.display_type)
        if not lines_to_recompute:
            return
        lines_to_recompute.invalidate_recordset(['pricelist_item_id', 'price_unit', 'discount'])
        lines_to_recompute._compute_pricelist_item_id()
        lines_to_recompute._compute_price_unit()
        lines_to_recompute._compute_discount()
        lines_to_recompute._compute_amount()  # subtotal / total
    def _get_display_price_ignore_combo(self):
        self.ensure_one()
        pricelist_price = self._get_pricelist_price()
        if not self.pricelist_item_id or not self.pricelist_item_id._show_discount():
            return pricelist_price
        base_price = self._get_pricelist_price_before_discount()
        return max(base_price, pricelist_price)

    def _get_pricelist_price(self):
        self.ensure_one()
        self.product_id.ensure_one()
        order_date = self.lead_id.date_last_stage_update.date()
        date = order_date or fields.Date.today()
        price = self.pricelist_item_id._compute_price(
            product=self.product_id.with_context(**self._get_product_price_context()),
            quantity=self.product_uom_qty or 1.0,
            uom=self.product_uom,
            date=date,
            currency=self.currency_id,
        )

        return price

    def _get_product_price_context(self):
        self.ensure_one()
        return self.product_id._get_product_price_context(
            self.product_no_variant_attribute_value_ids,
        )

  
    def _get_pricelist_price_before_discount(self):
        self.ensure_one()
        self.product_id.ensure_one()
        order_date = self.lead_id.date_last_stage_update.date()
        date = order_date or fields.Date.today()
        return self.pricelist_item_id._compute_price_before_discount(
            product=self.product_id.with_context(**self._get_product_price_context()),
            quantity=self.product_uom_qty or 1.0,
            uom=self.product_uom,
            date=self.lead_id.date,
            currency=self.currency_id,
        )

    @api.depends('product_id', 'product_uom', 'product_uom_qty')
    def _compute_discount(self):
        discount_enabled = self.env['product.pricelist.item']._is_discount_feature_enabled()
        for line in self:
            if not line.product_id or line.display_type:
                line.discount = 0.0

            if not (line.lead_id.pricelist_id and discount_enabled):
                continue

            line.discount = 0.0

            if not line.pricelist_item_id._show_discount():
                continue

            line = line.with_company(line.company_id)
            pricelist_price = line._get_pricelist_price()
            base_price = line._get_pricelist_price_before_discount()

            if base_price != 0:  # Avoid division by zero
                discount = (base_price - pricelist_price) / base_price * 100
                if (discount > 0 and base_price > 0) or (discount < 0 and base_price < 0):
                    line.discount = discount



    @api.depends('price_unit', 'discount')
    def _compute_price_reduce(self):
        for line in self:
            line.price_reduce = line.price_unit * (1.0 - line.discount / 100.0)

    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        self.ensure_one()
        return self.env['account.tax']._prepare_base_line_for_taxes_computation(
            self,
            **{
                # 'tax_ids': self.tax_id,
                'quantity': self.product_uom_qty,
                'partner_id': self.lead_id.partner_id,
                'currency_id': self.lead_id.currency_id or self.lead_id.company_currency_id,
                'rate': self.lead_id.currency_rate,
                **kwargs,
            },
        )

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount(self):
        for line in self:
            base_line = line._prepare_base_line_for_taxes_computation()
            self.env['account.tax']._add_tax_details_in_base_line(base_line, line.company_id)
            line.price_subtotal = base_line['tax_details']['raw_total_excluded_currency']
            line.price_total = base_line['tax_details']['raw_total_included_currency']
            line.price_tax = line.price_total - line.price_subtotal

    @api.depends('price_subtotal', 'product_uom_qty')
    def _compute_price_reduce_taxexcl(self):
        for line in self:
            line.price_reduce_taxexcl = line.price_subtotal / line.product_uom_qty if line.product_uom_qty else 0.0

    @api.depends('price_total', 'product_uom_qty')
    def _compute_price_reduce_taxinc(self):
        for line in self:
            line.price_reduce_taxinc = line.price_total / line.product_uom_qty if line.product_uom_qty else 0.0




    def _convert_to_sol_currency(self, amount, currency):
        self.ensure_one()
        to_currency = self.currency_id or self.lead_id.currency_id
        if currency and to_currency and currency != to_currency:
            order_date = self.lead_id.date_last_stage_update.date()
            date = order_date or fields.Date.today()
            # conversion_date = self.lead_id.date_last_stage_update or fields.Date.context_today(self)
            company = self.company_id or self.lead_id.company_id or self.env.company
            return currency._convert(
                from_amount=amount,
                to_currency=to_currency,
                company=company,
                date=date,
                round=False,
            )
        return amount

    def _add_precomputed_values(self, vals_list):
        super()._add_precomputed_values(vals_list)
        precision = self.env['decimal.precision'].precision_get('Discount')
        for vals in vals_list:
            if 'price_unit' in vals and 'technical_price_unit' not in vals:
                vals['technical_price_unit'] = vals['price_unit']
            if vals.get('discount'):
                vals['discount'] = float_round(vals['discount'], precision_digits=precision)

  

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('display_type') or self.default_get(['display_type']).get('display_type'):
                vals['product_uom_qty'] = 0.0

        lines = super().create(vals_list)
        quotation_count = len(self.lead_id.order_ids.filtered_domain(self.lead_id._get_lead_quotation_domain()))
        for line in lines:
            if line.product_id and quotation_count >0:
                msg = _("Extra line with %s", line.product_id.display_name)
                line.lead_id.message_post(body=msg)
        return lines



