from odoo import models, fields

class Movimiento(models.Model):
    _name = "sa.movimiento"  # Nombre técnico del modelo
    _description = "Movimiento Financiero"  # Descripción del modelo

    name = fields.Char(string="Descripción")  # Campo de texto corto
    monto = fields.Float(string="Monto")  # Campo numérico decimal
    tipo = fields.Selection(  # Campo de selección
        selection=[("I", "Ingreso"), ("G", "Gasto")],
        string="Tipo",
        required=True
    )
    fecha = fields.Date(string="Fecha")
    comprobante = fields.Binary(string="Comprobante")
    
    
    
    
    
# class saldoapp(models.Model):
#     _name = 'saldoapp.saldoapp'
#     _description = 'saldoapp.saldoapp'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

