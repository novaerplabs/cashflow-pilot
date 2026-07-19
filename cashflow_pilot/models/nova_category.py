from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class NovaCategory(models.Model):
    _name = 'nova.category'
    _description = 'Cash Flow Category'
    _order = 'direction, sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    direction = fields.Selection(
        [('in', 'Inflow'), ('out', 'Outflow')], required=True,
    )
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    company_id = fields.Many2one(
        'res.company', string='Company',
        help='Leave empty to share this category across all companies.',
    )
    active = fields.Boolean(default=True)

    @api.constrains('code', 'company_id')
    def _check_code_unique(self):
        for rec in self:
            if rec.company_id:
                domain = [
                    ('id', '!=', rec.id),
                    ('code', '=', rec.code),
                    '|', ('company_id', '=', False), ('company_id', '=', rec.company_id.id),
                ]
            else:
                domain = [('id', '!=', rec.id), ('code', '=', rec.code)]
            if self.search_count(domain):
                raise ValidationError(
                    _("A category with code '%s' already exists for this company.", rec.code)
                )
