
from odoo import http

class Saldoapp(http.Controller):
    @http.route('/saldoapp/saldoapp', auth='public')
    def index(self, **kw):
        return "HOLA MUNDOOOO"

#     @http.route('/saldoapp/saldoapp/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('saldoapp.listing', {
#             'root': '/saldoapp/saldoapp',
#             'objects': http.request.env['saldoapp.saldoapp'].search([]),
#         })

#     @http.route('/saldoapp/saldoapp/objects/<model("saldoapp.saldoapp"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('saldoapp.object', {
#             'object': obj
#         })

