"""
Test suite for market data functionality.
Tests market overview and top movers endpoints.
"""

import pytest
import json
from unittest.mock import patch
from datetime import datetime


@pytest.mark.api
@pytest.mark.unit
class TestMarketDataAPI:
    """Test class for market data API endpoints."""

    def test_get_market_overview_success(self, client, mock_db_session):
        """
        Test getting market overview with existing data.
        Should return formatted market indices data.
        """
        from db.models import MarketData
        
        # Create sample market data
        indices_data = [
            MarketData(
                id=1,
                symbol='SPY',
                index_name='S&P 500',
                type='index',
                current_value=450.75,
                percentage_change=1.25,
                timestamp=datetime.now()
            ),
            MarketData(
                id=2,
                symbol='QQQ',
                index_name='NASDAQ',
                type='index',
                current_value=375.50,
                percentage_change=-0.75,
                timestamp=datetime.now()
            ),
            MarketData(
                id=3,
                symbol='DIA',
                index_name='Dow Jones',
                type='index',
                current_value=340.25,
                percentage_change=0.5,
                timestamp=datetime.now()
            )
        ]
        
        for data in indices_data:
            mock_db_session.add(data)
        mock_db_session.commit()

        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session
            
            response = client.get('/api/market/overview')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 3
            
            # Check first index (SPY)
            spy_data = data[0]
            assert spy_data['name'] == 'S&P 500'
            assert spy_data['value'] == '$450.75'
            assert spy_data['change'] == '+1.2%'
            assert spy_data['trend'] == 'up'
            
            # Check second index (QQQ) - negative change
            qqq_data = data[1]
            assert qqq_data['name'] == 'NASDAQ'
            assert qqq_data['value'] == '$375.50'
            assert qqq_data['change'] == '-0.8%'
            assert qqq_data['trend'] == 'down'

    def test_get_market_overview_no_data(self, client, mock_db_session):
        """
        Test getting market overview when no data exists.
        Should return 404 error.
        """
        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session
            
            response = client.get('/api/market/overview')

            assert response.status_code == 404
            data = json.loads(response.data)
            assert 'error' in data
            assert data['error'] == 'No market data available'

    def test_get_market_overview_symbol_fallback(self, client, mock_db_session):
        """
        Test market overview when index_name is not available.
        Should use symbol as fallback for name.
        """
        from db.models import MarketData
        
        # Create data without index_name
        market_data = MarketData(
            id=1,
            symbol='VTI',
            index_name=None,  # No index name
            type='index',
            current_value=225.50,
            percentage_change=0.8,
            timestamp=datetime.now()
        )
        
        mock_db_session.add(market_data)
        mock_db_session.commit()

        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session
            
            response = client.get('/api/market/overview')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 1
            assert data[0]['name'] == 'VTI'  # Should use symbol as fallback

    def test_get_top_movers_success(self, client, mock_db_session):
        """
        Test getting top movers with existing stock data.
        Should return formatted stock data with volume.
        """
        from db.models import MarketData
        
        # Create sample stock data
        stocks_data = [
            MarketData(
                id=1,
                symbol='AAPL',
                company_name='Apple Inc.',
                type='stock',
                current_value=175.25,
                percentage_change=3.2,
                volume=50000000,
                timestamp=datetime.now()
            ),
            MarketData(
                id=2,
                symbol='MSFT',
                company_name='Microsoft Corporation',
                type='stock',
                current_value=420.75,
                percentage_change=-1.5,
                volume=25000000,
                timestamp=datetime.now()
            ),
            MarketData(
                id=3,
                symbol='GOOGL',
                company_name='Alphabet Inc.',
                type='stock',
                current_value=2850.50,
                percentage_change=2.8,
                volume=15000000,
                timestamp=datetime.now()
            )
        ]
        
        for data in stocks_data:
            mock_db_session.add(data)
        mock_db_session.commit()

        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session
            
            response = client.get('/api/market/top-movers')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 3
            
            # Check AAPL data
            aapl_data = data[0]
            assert aapl_data['symbol'] == 'AAPL'
            assert aapl_data['name'] == 'Apple Inc.'
            assert aapl_data['price'] == '$175.25'
            assert aapl_data['change'] == '+3.2%'
            assert aapl_data['volume'] == '50.0M'
            
            # Check MSFT data (negative change)
            msft_data = data[1]
            assert msft_data['symbol'] == 'MSFT'
            assert msft_data['name'] == 'Microsoft Corporation'
            assert msft_data['price'] == '$420.75'
            assert msft_data['change'] == '-1.5%'
            assert msft_data['volume'] == '25.0M'

    def test_get_top_movers_no_data(self, client, mock_db_session):
        """
        Test getting top movers when no data exists.
        Should return 404 error.
        """
        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session
            
            response = client.get('/api/market/top-movers')

            assert response.status_code == 404
            data = json.loads(response.data)
            assert 'error' in data
            assert data['error'] == 'No stock data available'

    def test_get_top_movers_no_volume(self, client, mock_db_session):
        """
        Test top movers when volume data is not available.
        Should show 'N/A' for volume.
        """
        from db.models import MarketData
        
        # Create stock data without volume
        stock_data = MarketData(
            id=1,
            symbol='TSLA',
            company_name='Tesla Inc.',
            type='stock',
            current_value=250.75,
            percentage_change=4.5,
            volume=None,  # No volume data
            timestamp=datetime.now()
        )
        
        mock_db_session.add(stock_data)
        mock_db_session.commit()

        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session
            
            response = client.get('/api/market/top-movers')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 1
            assert data[0]['volume'] == 'N/A'

    def test_get_top_movers_company_name_fallback(self, client, mock_db_session):
        """
        Test top movers when company_name is not available.
        Should use symbol as fallback for name.
        """
        from db.models import MarketData
        
        # Create stock data without company name
        stock_data = MarketData(
            id=1,
            symbol='NVDA',
            company_name=None,  # No company name
            type='stock',
            current_value=875.25,
            percentage_change=5.2,
            volume=30000000,
            timestamp=datetime.now()
        )
        
        mock_db_session.add(stock_data)
        mock_db_session.commit()

        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session
            
            response = client.get('/api/market/top-movers')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 1
            assert data[0]['name'] == 'NVDA'  # Should use symbol as fallback

    def test_market_overview_database_error(self, client):
        """
        Test market overview when database error occurs.
        Should return 500 error with error message.
        """
        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.side_effect = Exception('Database connection failed')
            
            response = client.get('/api/market/overview')

            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data

    def test_top_movers_database_error(self, client):
        """
        Test top movers when database error occurs.
        Should return 500 error with error message.
        """
        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.side_effect = Exception('Database connection failed')
            
            response = client.get('/api/market/top-movers')

            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data

    def test_market_overview_percentage_formatting(self, client, mock_db_session):
        """
        Test that percentage changes are properly formatted.
        Should handle zero, positive, and negative values correctly.
        """
        from db.models import MarketData
        
        # Create data with different percentage changes
        test_data = [
            MarketData(
                id=1,
                symbol='ZERO',
                index_name='Zero Change',
                type='index',
                current_value=100.0,
                percentage_change=0.0,
                timestamp=datetime.now()
            ),
            MarketData(
                id=2,
                symbol='POS',
                index_name='Positive Change',
                type='index',
                current_value=100.0,
                percentage_change=2.5,
                timestamp=datetime.now()
            ),
            MarketData(
                id=3,
                symbol='NEG',
                index_name='Negative Change',
                type='index',
                current_value=100.0,
                percentage_change=-1.8,
                timestamp=datetime.now()
            )
        ]
        
        for data in test_data:
            mock_db_session.add(data)
        mock_db_session.commit()

        with patch('apis.market_data.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session
            
            response = client.get('/api/market/overview')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 3
            
            # Check formatting
            assert data[0]['change'] == '+0.0%'  # Zero with plus
            assert data[0]['trend'] == 'up'
            
            assert data[1]['change'] == '+2.5%'  # Positive with plus
            assert data[1]['trend'] == 'up'
            
            assert data[2]['change'] == '-1.8%'  # Negative without plus
            assert data[2]['trend'] == 'down' 