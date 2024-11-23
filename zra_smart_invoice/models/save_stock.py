from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def create_credit_note_payload(self):
        company = self.env.company
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "orgInvcNo": 78687,
            "cisInvcNo": "SAP000019",
            "custTin": "0782229123",
            "custNm": "Test Customer",
            "salesTyCd": "N",
            "rcptTyCd": "R",
            "pmtTyCd": "01",
            "salesSttsCd": "02",
            "cfmDt": "20240502102010",
            "salesDt": "20240502",
            "stockRlsDt": None,
            "cnclReqDt": None,
            "cnclDt": None,
            "rfdDt": None,
            "rfdRsnCd": "01",
            "totItemCnt": 1,
            "taxblAmtA": 86.2069,
            "taxblAmtB": 0.0,
            "taxblAmtC": 0.0,
            "taxblAmtC1": 0.0,
            "taxblAmtC2": 0.0,
            "taxblAmtC3": 0.0,
            "taxblAmtD": 0.0,
            "taxblAmtRvat": 0.0,
            "taxblAmtE": 0.0,
            "taxblAmtF": 0.0,
            "taxblAmtIpl1": 0,
            "taxblAmtIpl2": 0.0,
            "taxblAmtTl": 0,
            "taxblAmtEcm": 0,
            "taxblAmtExeeg": 0.0,
            "taxblAmtTot": 0.0,
            "taxRtA": 16,
            "taxRtB": 16,
            "taxRtC1": 0,
            "taxRtC2": 0,
            "taxRtC3": 0,
            "taxRtD": 0,
            "taxRtRvat": 16,
            "taxRtE": 0,
            "taxRtF": 10,
            "taxRtIpl1": 5,
            "taxRtIpl2": 0,
            "taxRtTl": 1.5,
            "taxRtEcm": 5,
            "taxRtExeeg": 3,
            "taxRtTot": 0,
            "taxAmtA": 13.7931,
            "taxAmtB": 0.0,
            "taxAmtC": 0.0,
            "taxAmtC1": 0.0,
            "taxAmtC2": 0.0,
            "taxAmtC3": 0.0,
            "taxAmtD": 0.0,
            "taxAmtRvat": 0.0,
            "taxAmtE": 0.0,
            "taxAmtF": 0,
            "taxAmtIpl1": 0,
            "taxAmtIpl2": 0.0,
            "taxAmtTl": 0,
            "taxAmtEcm": 0.0,
            "taxAmtExeeg": 0.0,
            "taxAmtTot": 0.0,
            "totTaxblAmt": 86.2069,
            "totTaxAmt": 13.7931,
            "totAmt": 100,
            "prchrAcptcYn": "N",
            "remark": "",
            "regrId": "admin",
            "regrNm": "admin",
            "modrId": "admin",
            "modrNm": "admin",
            "saleCtyCd": "1",
            "lpoNumber": "ZM2379729723",
            "currencyTyCd": "ZMW",
            "exchangeRt": "1",
            "destnCountryCd": "",
            "dbtRsnCd": "",
            "invcAdjustReason": "",
            "itemList": [
                {
                    "itemSeq": 1,
                    "itemCd": "20044",
                    "itemClsCd": "50102517",
                    "itemNm": "Chicken Wings",
                    "bcd": "",
                    "pkgUnitCd": "BA",
                    "pkg": 0.0,
                    "qtyUnitCd": "BE",
                    "qty": 1.0,
                    "prc": 100.0,
                    "splyAmt": 100.0,
                    "dcRt": 0.0,
                    "dcAmt": 0.0,
                    "isrccCd": "",
                    "isrccNm": "",
                    "isrcRt": 0.0,
                    "isrcAmt": 0.0,
                    "vatCatCd": "A",
                    "exciseTxCatCd": None,
                    "vatTaxblAmt": 86.2069,
                    "exciseTaxblAmt": 0,
                    "vatAmt": 13.7931,
                    "exciseTxAmt": 0,
                    "totAmt": 100
                }
            ]
        }
        return payload

    def create_credit_note_api_call(self):
        api_url = "http://vsdc.iswe.co.zm/sandbox/trnsSales/saveSales"
        payload = self.create_credit_note_payload()
        return self._post_to_api(api_url, payload, "API Response Credit Note")

    def refund_moves(self):
        res = super(AccountMoveReversal, self).refund_moves()
        self._process_moves()
        return res

    def modify_moves(self):
        res = super(AccountMoveReversal, self).modify_moves()
        self._process_moves()
        return res

    def _process_moves(self):
        for move in self.move_ids:
            # Process credit note API call
            result_msg = self.create_credit_note_api_call()
            move.message_post(body=f"API Response Credit Note resultMsg: {result_msg}")
            # print(f"API Response Credit Note resultMsg: {result_msg}")
            company = self.env.company

            payload_new_endpoint = {
                "tpin": company.tpin,
                "bhfId": company.bhf_id,
                "sarNo": 1,
                "orgSarNo": 0,
                "regTyCd": "M",
                "custTpin": None,
                "custNm": None,
                "custBhfId": "000",
                "sarTyCd": "13",
                "ocrnDt": "20200126",
                "totItemCnt": 2,
                "totTaxblAmt": 70000,
                "totTaxAmt": 12000,
                "totAmt": 70000,
                "remark": None,
                "regrId": "Admin",
                "regrNm": "Admin",
                "modrNm": "Admin",
                "modrId": "Admin",
                "itemList": [
                    {
                        "itemSeq": 1,
                        "itemCd": "RW1NTXU0000006",
                        "itemClsCd": "5059690800",
                        "itemNm": "AMAZI Rwenzoli",
                        "bcd": None,
                        "pkgUnitCd": "NT",
                        "pkg": 10,
                        "qtyUnitCd": "U",
                        "qty": 10,
                        "itemExprDt": None,
                        "prc": 3500,
                        "splyAmt": 35000,
                        "totDcAmt": 0,
                        "taxblAmt": 35000,
                        "vatCatCd": "A",
                        "iplCatCd": "IPL1",
                        "tlCatCd": "TL",
                        "exciseTxCatCd": "EXEEG",
                        "vatAmt": 30508,
                        "iplAmt": 30508,
                        "tlAmt": 30508,
                        "exciseTxAmt": 30508,
                        "taxAmt": 6000,
                        "totAmt": 35000
                    },
                    {
                        "itemSeq": 2,
                        "itemCd": "RW2TYXLTR0000001",
                        "itemClsCd": "5059690800",
                        "itemNm": "MAZUT",
                        "bcd": None,
                        "pkgUnitCd": "NT",
                        "pkg": 10,
                        "qtyUnitCd": "U",
                        "qty": 10,
                        "itemExprDt": None,
                        "prc": 3500,
                        "splyAmt": 35000,
                        "totDcAmt": 0,
                        "taxblAmt": 35000,
                        "vatCatCd": "A",
                        "iplCatCd": "IPL1",
                        "tlCatCd": "TL",
                        "exciseTxCatCd": "EXEEG",
                        "vatAmt": 30508,
                        "iplAmt": 30508,
                        "tlAmt": 30508,
                        "exciseTxAmt": 30508,
                        "totAmt": 35000
                    }
                ]
            }
            result_msg_new_endpoint = self._post_to_api('http://vsdc.iswe.co.zm/sandbox/stock/saveStockItems',
                                                        payload_new_endpoint, "Save Stock Item API Response")
            move.message_post(body=f"API Response New Endpoint: {result_msg_new_endpoint}")
            # print(f"Save Stock Item API Response: {result_msg_new_endpoint}")

            payload_stock = {
                "tpin": company.tpin,
                "bhfId": company.bhf_id,
                "regrId": "Admin",
                "regrNm": "Admin",
                "modrNm": "Admin",
                "modrId": "Admin",
                "stockItemList": [
                    {
                        "itemCd": "RW1NTXU0000001",
                        "rsdQty": 4
                    }
                ]
            }
            result_msg_stock = self._post_to_api('http://vsdc.iswe.co.zm/sandbox/stockMaster/saveStockMaster', payload_stock,
                                                 "Save Stock Master Endpoint response:")
            move.message_post(body=f"Endpoint response: {result_msg_stock}")
            # print(f"Save Stock Master Endpoint response: {result_msg_stock}")

    def _post_to_api(self, url, payload, success_message_prefix):
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            result_msg = response.json().get('resultMsg', 'No result message returned')
            _logger.info(f'{success_message_prefix}: {result_msg}')
            print(f'{success_message_prefix}: {result_msg}')
            return result_msg
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            _logger.error(f'API request failed: {error_msg}')
            print(f'API request failed: {error_msg}')
            return f"Error during API call: {error_msg}"
