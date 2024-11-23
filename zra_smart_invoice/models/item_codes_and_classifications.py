from odoo import models, fields, api
import logging
import requests

_logger = logging.getLogger(__name__)


class ZraItemData(models.Model):
    _name = 'zra.item.data'
    _description = 'ZRA Item Data'
    _rec_name = 'itemClsNm'  # Specify the field to be used as the name

    itemClsCd = fields.Char(string='Item Classification Code')
    itemClsNm = fields.Char(string='Item Classification Name')
    itemClsLvl = fields.Integer(string='Item Classification Level')
    taxTyCd = fields.Char(string='Tax Type Code')
    mjrTgYn = fields.Char(string='Major Target')
    useYn = fields.Char(string='Use')

    @api.model
    def fetch_and_store_classification_data(self):
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        company = self.env.company
        url = config_settings.classification_endpoint
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "lastReqDt": "20240123121449"
        }
        headers = {
            'Content-Type': 'application/json'
        }
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            # ResConfigSettings.endpoint_hit_counts['endpoint_1'] += 1
            data = response.json().get('data', {}).get('itemClsList', [])
            self.sudo().search([]).unlink()  # Clear existing records
            for item in data:
                if item['useYn'] == 'Y':
                    self.create({
                        'itemClsCd': item['itemClsCd'],
                        'itemClsNm': item['itemClsNm'],
                        'itemClsLvl': item['itemClsLvl'],
                        'taxTyCd': item.get('taxTyCd', ''),
                        'mjrTgYn': item.get('mjrTgYn', ''),
                        'useYn': item['useYn']
                    })
        except requests.exceptions.RequestException as e:
            _logger.error('Failed to fetch classification data from ZRA: %s', e)


class CodeData(models.AbstractModel):
    _name = 'code.data'
    _description = 'Common Code Data'

    @api.model
    def fetch_common_code_data(self):
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        company = self.env.company
        url = config_settings.class_codes_endpoint
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "lastReqDt": "20180520000000"
        }
        headers = {
            'Content-Type': 'application/json'
        }
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            # ResConfigSettings.endpoint_hit_counts['endpoint_2'] += 1
            return response.json().get('data', {}).get('clsList', [])
        except requests.exceptions.RequestException as e:
            _logger.error('Failed to fetch common code data: %s', e)
            return []


class QuantityUnitData(models.Model):
    _name = 'quantity.unit.data'
    _description = 'Quantity Unit Data'
    _rec_name = 'quantity_unit_cdNm'  # Specify the field to be used as the name

    quantity_unit_cd = fields.Char(string='Quantity Unit Code')
    quantity_unit_cdNm = fields.Char(string='Quantity Unit Name')

    @api.model
    def store_quantity_data(self, data):
        self.sudo().search([]).unlink()  # Clear existing records
        for cls_item in data:
            if cls_item['cdCls'] == '10':
                for item in cls_item.get('dtlList', []):
                    self.create({
                        'quantity_unit_cd': item['cd'],
                        'quantity_unit_cdNm': item['cdNm']
                    })


class PackagingUnitData(models.Model):
    _name = 'packaging.unit.data'
    _description = 'Packaging Unit Data'
    _rec_name = 'packaging_unit_cdNm'  # Specify the field to be used as the name

    packaging_unit_cd = fields.Char(string='Packaging Unit Code')
    packaging_unit_cdNm = fields.Char(string='Packaging Unit Name')

    @api.model
    def store_packaging_data(self, data):
        self.sudo().search([]).unlink()  # Clear existing records
        for cls_item in data:
            if cls_item['cdCls'] == '17':
                for item in cls_item.get('dtlList', []):
                    self.create({
                        'packaging_unit_cd': item['cd'],
                        'packaging_unit_cdNm': item['cdNm']
                    })


class CountryData(models.Model):
    _name = 'country.data'
    _description = 'Country Data'
    _rec_name = 'country_cdNm'  # Specify the field to be used as the name

    country_cd = fields.Char(string='Country Code')
    country_cdNm = fields.Char(string='Country Name')

    @api.model
    def store_country_data(self, data):
        self.sudo().search([]).unlink()  # Clear existing records
        for cls_item in data:
            if cls_item['cdCls'] == '05':
                for item in cls_item.get('dtlList', []):
                    self.create({
                        'country_cd': item['cd'],
                        'country_cdNm': item['cdNm']
                    })
