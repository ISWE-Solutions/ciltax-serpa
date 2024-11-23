from symtable import Class

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fetch_data_button = fields.Boolean(string="Fetch Data")

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

    # Newly added fields
    import_update_endpoint = fields.Char(string='Import Update ZRA Endpoint',
                                         default="http://vsdc.iswe.co.zm/sandbox/imports/updateImportItems")
    inventory_update_endpoint = fields.Char(string='Inventory Update ZRA Endpoint',
                                            default="http://vsdc.iswe.co.zm/sandbox/items/updateItem")

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        params = self.env['ir.config_parameter'].sudo()

        params.set_param('res.config.settings.classification_endpoint', self.classification_endpoint)
        params.set_param('res.config.settings.class_codes_endpoint', self.class_codes_endpoint)
        params.set_param('res.config.settings.sales_endpoint', self.sales_endpoint)
        params.set_param('res.config.settings.purchase_endpoint', self.purchase_endpoint)
        params.set_param('res.config.settings.purchase_si_endpoint', self.purchase_si_endpoint)
        params.set_param('res.config.settings.inventory_endpoint', self.inventory_endpoint)
        params.set_param('res.config.settings.import_endpoint', self.import_endpoint)
        params.set_param('res.config.settings.stock_io_endpoint', self.stock_io_endpoint)
        params.set_param('res.config.settings.stock_master_endpoint', self.stock_master_endpoint)
        params.set_param('res.config.settings.import_update_endpoint', self.import_update_endpoint)
        params.set_param('res.config.settings.inventory_update_endpoint', self.inventory_update_endpoint)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()

        res.update(
            classification_endpoint=params.get_param('res.config.settings.classification_endpoint',
                                                     default="http://vsdc.iswe.co.zm/sandbox/itemClass/selectItemsClass"),
            class_codes_endpoint=params.get_param('res.config.settings.class_codes_endpoint',
                                                  default="http://vsdc.iswe.co.zm/sandbox/code/selectCodes"),
            sales_endpoint=params.get_param('res.config.settings.sales_endpoint',
                                            default="http://vsdc.iswe.co.zm/sandbox/trnsSales/saveSales"),
            purchase_endpoint=params.get_param('res.config.settings.purchase_endpoint',
                                               default="http://vsdc.iswe.co.zm/sandbox/trnsPurchase/savePurchase"),
            purchase_si_endpoint=params.get_param('res.config.settings.purchase_si_endpoint',
                                                  default="http://vsdc.iswe.co.zm/sandbox/trnsPurchase/selectTrnsPurchaseSales"),
            inventory_endpoint=params.get_param('res.config.settings.inventory_endpoint',
                                                default="http://vsdc.iswe.co.zm/sandbox/items/saveItem"),
            import_endpoint=params.get_param('res.config.settings.import_endpoint',
                                             default="http://vsdc.iswe.co.zm/sandbox/imports/selectImportItems"),
            stock_io_endpoint=params.get_param('res.config.settings.stock_io_endpoint',
                                               default="http://vsdc.iswe.co.zm/sandbox/stock/saveStockItems"),
            stock_master_endpoint=params.get_param('res.config.settings.stock_master_endpoint',
                                                   default="http://vsdc.iswe.co.zm/sandbox/stockMaster/saveStockMaster"),
            import_update_endpoint=params.get_param('res.config.settings.import_update_endpoint',
                                                    default="http://vsdc.iswe.co.zm/sandbox/imports/updateImportItems"),
            inventory_update_endpoint=params.get_param('res.config.settings.inventory_update_endpoint',
                                                       default="http://vsdc.iswe.co.zm/sandbox/items/updateItem"),
        )
        return res

    @api.model
    def create(self, vals):
        # Delete any existing rows
        self.sudo().search([]).unlink()
        # Create the new record
        return super(ResConfigSettings, self).create(vals)

    def write(self, vals):
        # Delete any existing rows before writing new data
        self.sudo().search([]).unlink()
        # Write the new record
        return super(ResConfigSettings, self).write(vals)



    endpoint_hit_counts = {
        'endpoint_1': 0,
        'endpoint_2': 0
    }





    def fetch_data(self):
        self.env['zra.item.data'].fetch_and_store_classification_data()
        common_data = self.env['code.data'].fetch_common_code_data()
        self.env['quantity.unit.data'].store_quantity_data(common_data)
        self.env['packaging.unit.data'].store_packaging_data(common_data)
        self.env['country.data'].store_country_data(common_data)
        _logger.info("Data fetched and stored successfully.")

        print(f"Endpoint 1 hit {self.endpoint_hit_counts['endpoint_1']} time(s)")
        print(f"Endpoint 2 hit {self.endpoint_hit_counts['endpoint_2']} time(s)")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Data fetched and stored successfully.',
                'type': 'success',
                'sticky': False,
            }
        }