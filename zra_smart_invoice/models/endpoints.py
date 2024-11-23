from odoo import models, fields, api, _


class Endpoints(models.Model):
    _inherit = 'res.company'

    fetch_data_button = fields.Boolean(string="Fetch Data")

    initialization_endpoint = fields.Char(string='initialization  ZRA Endpoint',
                                          default="http://vsdc.iswe.co.zm/sandbox/initializer/selectInitInfo")

    classification_endpoint = fields.Char(string='classification  ZRA Endpoint',
                                          default="http://vsdc.iswe.co.zm/sandbox/itemClass/selectItemsClass")
    class_codes_endpoint = fields.Char(string='class codes ZRA Endpoint',
                                       default="http://vsdc.iswe.co.zm/sandbox/code/selectCodes")
    sales_endpoint = fields.Char(string='Sales ZRA Endpoint', default="http://vsdc.iswe.co.zm/sandbox/trnsSales/saveSales")
    purchase_endpoint = fields.Char(string='Purchase ZRA Endpoint',
                                    default="http://vsdc.iswe.co.zm/sandbox/trnsPurchase/savePurchase")
    purchase_si_endpoint = fields.Char(string='Purchase SI ZRA Endpoint',
                                       default="http://vsdc.iswe.co.zm/sandbox/trnsPurchase/selectTrnsPurchaseSales")
    inventory_endpoint = fields.Char(string='Inventory ZRA Endpoint', default="http://vsdc.iswe.co.zm/sandbox/items/saveItem")
    import_endpoint = fields.Char(string='Import ZRA Endpoint',
                                  default="http://vsdc.iswe.co.zm/sandbox/imports/selectImportItems")
    stock_io_endpoint = fields.Char(string='Stock I/O ZRA Endpoint',
                                    default="http://vsdc.iswe.co.zm/sandbox/stock/saveStockItems")
    stock_master_endpoint = fields.Char(string='Stock Master ZRA Endpoint',
                                        default="http://vsdc.iswe.co.zm/sandbox/stockMaster/saveStockMaster")

    import_update_endpoint = fields.Char(string='Import Update ZRA Endpoint',
                                         default="http://vsdc.iswe.co.zm/sandbox/imports/updateImportItems")
    inventory_update_endpoint = fields.Char(string='Inventory Update ZRA Endpoint',
                                            default="http://vsdc.iswe.co.zm/sandbox/items/updateItem")

    @api.model
    def create(self, vals):
        # Proceed with the creation of the new record
        return super(Endpoints, self).create(vals)

    def write(self, vals):
        # Proceed with updating the current record
        return super(Endpoints, self).write(vals)

