# -*- coding: utf-8 -*-
#################################################################################
# Author      : Zero For Information Systems (<www.erpzero.com>)
# Copyright(c): 2016-Zero For Information Systems
# All Rights Reserved.
#zerosystems #erp #odoo
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################
{
    'name': "CRM | Opportunity | Lead Line Products",
    'author': 'Zero Systems',
    'website': "http://erpzero.com",
    'live_test_url': 'https://youtu.be/643WhbrZ0IE',
    'category': 'Sales/CRM',
    'version': '9.4',
    "sequence": 0,
    'license': 'OPL-1',
    'demo': [],
    "depends" : ['account','sale_management','sale_crm'],
    'summary': """
        CRM Opportunity Lead Products work items""",
    'description': """
        Add Products and Services to CRM Lead / Opportunity
        Pipeline Product to Sales Order | CRM Product to Quotation
        Pipeline Product to Quotation CRM Product to Sales Order CRM Product to Sale Order add products on pipeline to quotation add product
        on pipeline to sales order product from lead add product on lead to quotation add product on crm pipeline to quote product
        CRM Product to Quotation Odoo App helps users to easily create, manage, and track quotation directly from the pipeline view.
        This app integrates seamlessly with the CRM, allowing users to add multiple product to lead or pipeline, and create sales quotation directly from the CRM. This makes it easy to create accurate and detailed quotation that are tailored to the specific needs of each customer.
        In addition, the app allows users to track the quotation from CRM using smart buttons
        Add any Product Type "Storable Product - Consumable - Service " To lead/Opportunity in CRM
        Support Price List related CRM users defined by default in user partner ID profile. 
        Opportunity Expected Revenue Computed by Net Total Amount "Products/Services Lines"
        Duplicate opportunity will Duplicate All Products Line .
        Add Note Line And Section Line to Opportunity and Transfer to Quotation with Products Lines.
        Pricelist Changed Automatics related Customer if customer defined to lead/Opportunity.
        Support Multi Currency and currency automatics related Price List Currency.
        Support Fiscal Position.
        Add Payment Terms Related Opportunity
        New menu To Manage Products, Product Variants, Products Attribute and Pricelist  Also from CRM.
        When Create Quotation from Opportunity System will transfer All New Fields to Quotation.
    """,
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
    ],
    "price": 10.00,
    "currency": 'EUR',
    'installable': True,
    'auto_install': False,
    "application": True,
    'pre_init_hook': 'pre_init_check',
    'images': ['static/description/icon.png'],
}
