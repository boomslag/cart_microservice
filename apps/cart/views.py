from rest_framework.response import Response
from rest_framework import status
from rest_framework import permissions
from rest_framework.parsers import JSONParser
from django.shortcuts import get_object_or_404
from rest_framework_api.views import StandardAPIView
from django.core.cache import cache
import jwt
import requests
from decimal import Decimal
import uuid
from .serializers import CartItemSerializer, CartSerializer
import aiohttp
from asgiref.sync import async_to_sync
from .models import Cart, CartItem
from django.conf import settings
secret_key = settings.SECRET_KEY
taxes = settings.TAXES
courses_ms_url = settings.COURSES_MS_URL
coupons_ms_url = settings.COUPONS_MS_URL
products_ms_url = settings.PRODUCTS_MS_URL


def validate_token(request):
    token = request.META.get('HTTP_AUTHORIZATION').split()[1]

    try:
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return Response({"error": "Token has expired."}, status=status.HTTP_401_UNAUTHORIZED)
    except jwt.DecodeError:
        return Response({"error": "Token is invalid."}, status=status.HTTP_401_UNAUTHORIZED)
    except Exception:
        return Response({"error": "An error occurred while decoding the token."}, status=status.HTTP_401_UNAUTHORIZED)

    return payload


# Create your views here.
class GetCartView(StandardAPIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, userID, format=None):
        # Get cart
        cart = Cart.objects.get(user=userID)
        serializer = CartSerializer(cart).data
        return self.send_response(serializer, status=status.HTTP_200_OK)


class GetItemsView(StandardAPIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, format=None):
        payload = validate_token(request)
        user_id = payload.get('user_id', None)

        if user_id is not None:
            cart = Cart.objects.get(user=user_id)
            total_items = cart.total_items
            cart_items = CartItem.objects.filter(cart=cart)

            items = []

            if CartItem.objects.filter(cart=cart).exists():
                for cart_item in cart_items:
                    item = {}
                    item['id'] = cart_item.id
                    item['count'] = cart_item.count
                    item['product'] = cart_item.product
                    item['course'] = cart_item.course
                    item['size'] = cart_item.size
                    item['weight'] = cart_item.weight
                    item['material'] = cart_item.material
                    item['color'] = cart_item.color
                    item['shipping'] = cart_item.shipping
                    item['coupon'] = cart_item.coupon
                    item['referrer'] = cart_item.referrer

                    items.append(item)

            return self.send_response({
                'cart': items,
                'total_items': total_items,
            }, status=status.HTTP_200_OK)
        else:
            return self.send_response({}, status=status.HTTP_200_OK)
    

class GetTotalView(StandardAPIView):
    permission_classes = (permissions.AllowAny,)

    async def async_get_response(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.json()

    async def get_course_response(self, course):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{courses_ms_url}/api/courses/get/{course}/") as response:
                return await response.json()

    async def get_coupon_response(self, coupon):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{coupons_ms_url}/api/coupons/get/{coupon}/") as response:
                return await response.json()

    async def get_product_response(self, product):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{products_ms_url}/api/products/get/{product}/") as response:
                json_response = await response.json()
        return json_response['results']
    
    @async_to_sync
    async def post(self, request, format=None):
        data = JSONParser().parse(request)
        if not data:
            return self.send_response({
            'total_cost': 0,
            'total_cost_ethereum': 0,
            'maticCost': 0,
            'total_compare_cost': 0,
            'finalPrice': 0,
            'tax_estimate': 0,
            'shipping_estimate': 0,
            },status=status.HTTP_200_OK)
        courses = []
        products = []
        total_cost = Decimal(0)
        total_compare_cost = Decimal(0)
        tax_estimate = Decimal(0)
        shipping_estimate = Decimal(0)
        finalProductPrice = Decimal(0)
        finalCoursePrice = Decimal(0)
        finalPrice = Decimal(0)

        for item in data:
            if item.get('course'):
                courses.append(item)
            elif item.get('product'):
                products.append(item)

        for object in courses:
            # course = Course.objects.get(id=item['course'])
            course = object['course'] if object['course'] else None
            coupon = object['coupon'] if object['coupon'] else None

            
            # Check if course exists
            course_response = await self.get_course_response(course)
            
            if not course_response.get('results'):
                # If course does not exist, remove it from the cart
                CartItem.objects.filter(course=course).delete()
                continue

            if coupon:
                coupon_response = await self.get_coupon_response(coupon)
                coupon_fixed_price_coupon = coupon_response.get('fixed_price_coupon')
                coupon_percentage_coupon = coupon_response.get('percentage_coupon')
                
                if coupon_fixed_price_coupon:
                    coupon_fixed_discount_price = coupon_fixed_price_coupon['discount_price']
                else:
                    coupon_fixed_discount_price = None
                
                if coupon_percentage_coupon:
                    coupon_discount_percentage = coupon_percentage_coupon['discount_percentage']
                else:
                    coupon_discount_percentage = None

            else:
                coupon_fixed_price_coupon = None
                coupon_fixed_discount_price = None
                coupon_percentage_coupon = None
                coupon_discount_percentage = None

            course_price = course_response.get('results', {}).get('details', {}).get('price')
            course_compare_price = course_response.get('results').get('details').get('compare_price')
            course_discount = course_response.get('results').get('details').get('discount')

            # Calculate Total Cost Without Discounts and Coupons and Taxes (total_cost)
            if course_discount == False:
                total_cost += Decimal(course_price)
            else:
                total_cost += Decimal(course_compare_price)
            # Calculate Total Cost With Discount and Coupons if present (total_compare_cost)
            if course_discount == True:
                if coupon_fixed_discount_price is not None:
                    total_compare_cost += max(Decimal(course_compare_price) - Decimal(coupon_fixed_discount_price), 0)
                elif coupon_discount_percentage is not None:
                    total_compare_cost += Decimal(course_compare_price) * (1 - (Decimal(coupon_discount_percentage) / 100))
                else:
                    total_compare_cost += Decimal(course_compare_price)
            else:
                if coupon_fixed_discount_price is not None:
                    total_compare_cost += max(Decimal(course_price) - Decimal(coupon_fixed_discount_price), 0)
                elif coupon_discount_percentage is not None:
                    total_compare_cost += Decimal(course_price) * (1 - (Decimal(coupon_discount_percentage) / 100))
                else:
                    total_compare_cost += Decimal(course_price)
            
            # Calculate Taxes for Total Cost (tax_estimate)
            tax_estimate = Decimal(total_compare_cost) * Decimal(taxes)
            # print('Tax Estimate: ',tax_estimate )
            finalCoursePrice = Decimal(total_compare_cost) + Decimal(tax_estimate)
        
        for object in products:
            product = object.get('product', None)
            coupon = object.get('coupon', None)
            quantity = object.get('quantity', 1)  # set default quantity to 1 if not provided
            # print(object)

            base_price = Decimal('0')


            product_response = await self.get_product_response(product)
            if coupon:
                coupon_response = await self.get_coupon_response(coupon)
                coupon_fixed_price_coupon = coupon_response.get('fixed_price_coupon')
                coupon_percentage_coupon = coupon_response.get('percentage_coupon')
                
                if coupon_fixed_price_coupon:
                    coupon_fixed_discount_price = coupon_fixed_price_coupon['discount_price']
                else:
                    coupon_fixed_discount_price = None
                
                if coupon_percentage_coupon:
                    coupon_discount_percentage = coupon_percentage_coupon['discount_percentage']
                else:
                    coupon_discount_percentage = None

            else:
                coupon_fixed_price_coupon = None
                coupon_fixed_discount_price = None
                coupon_percentage_coupon = None
                coupon_discount_percentage = None

            # GET Shipping
            shipping_id = object['shipping']
            filtered_shipping = [shipping for shipping in product_response['shipping'] if shipping['id'] == shipping_id]
            selected_shipping = None
            if filtered_shipping:
                selected_shipping = filtered_shipping[0]
           
            # GET WEIGHT
            weight_id = object['weight']
            filtered_weights = [weight for weight in product_response['weights'] if weight['id'] == weight_id]
            selected_weight = None
            if filtered_weights:
                selected_weight = filtered_weights[0]
           
            # GET MATERIAL
            material_id = object['material']
            filtered_materials = [material for material in product_response['materials'] if material['id'] == material_id]
            selected_material = None
            if filtered_materials:
                selected_material = filtered_materials[0]
           
            # GET COLOR
            color_id = object['color']
            filtered_colors = [color for color in product_response['colors'] if color['id'] == color_id]
            selected_color = None
            if filtered_colors:
                selected_color = filtered_colors[0]
           
            # GET Size
            size_id = object['size']
            filtered_sizes = [size for size in product_response['sizes'] if size['id'] == size_id]
            selected_size = None
            if filtered_sizes:
                selected_size = filtered_sizes[0]

            product_price = product_response.get('details').get('price')
            product_compare_price = product_response.get('details').get('compare_price')
            product_discount = product_response.get('details').get('discount')

            if product_price is not None:
                base_price = Decimal(product_price)
            if selected_weight:
                base_price += Decimal(selected_weight.get('price'))
            if selected_material:
                base_price += Decimal(selected_material.get('price'))
            if selected_color:
                base_price += Decimal(selected_color.get('price'))
            if selected_size:
                base_price += Decimal(selected_size.get('price'))

            print("Base Price:", base_price)

            # Calculate Total Cost Without Discounts and Coupons and Taxes (total_cost)
            if product_discount == False:
                total_cost += Decimal(base_price) * quantity
            else:
                total_cost += Decimal(product_compare_price) * quantity

            # Calculate Total Cost With Discount and Coupons if present (total_compare_cost)
            if product_discount == True:
                if coupon_fixed_discount_price is not None:
                    total_compare_cost += max(Decimal(product_compare_price) - Decimal(coupon_fixed_discount_price), 0) * quantity
                elif coupon_discount_percentage is not None:
                    total_compare_cost += Decimal(product_compare_price) * (1 - (Decimal(coupon_discount_percentage) / 100)) * quantity
                else:
                    total_compare_cost += Decimal(product_compare_price) * quantity
            else:
                if coupon_fixed_discount_price is not None:
                    total_compare_cost += max(Decimal(base_price) - Decimal(coupon_fixed_discount_price), 0) * quantity
                elif coupon_discount_percentage is not None:
                    total_compare_cost += Decimal(base_price) * (1 - (Decimal(coupon_discount_percentage) / 100)) * quantity
                else:
                    total_compare_cost += Decimal(base_price) * quantity

            # Calculate shipping
            if product_response.get('shipping'):
                shipping_price = Decimal(selected_shipping.get('price'))
                shipping_estimate += shipping_price
                total_compare_cost += shipping_price

            # Calculate Taxes for Total Cost (tax_estimate)
            tax_estimate = Decimal(total_compare_cost) * Decimal(taxes)
            finalProductPrice = Decimal(total_compare_cost) + Decimal(tax_estimate)


        finalPrice = Decimal(finalProductPrice) + Decimal(finalCoursePrice)

        eth_price = cache.get('eth_price')
        matic_price = cache.get('matic_price')
        if not eth_price:
            eth_price_response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=matic-network%2Cethereum&vs_currencies=usd').json()
            eth_price = eth_price_response.get('ethereum').get('usd')
            matic_price = eth_price_response.get('matic-network').get('usd')
            cache.set('eth_price', eth_price, 1 * 60) # cache for 1 minutes
            cache.set('matic_price', matic_price, 1 * 60) # cache for 1 minutes
        ethCost = finalPrice / Decimal(eth_price)
        maticCost = finalPrice / Decimal(matic_price)

        return self.send_response({
            'total_cost': total_cost,
            'total_cost_ethereum': ethCost,
            'maticCost': maticCost,
            'total_compare_cost': total_compare_cost,
            'finalPrice': finalPrice,
            'tax_estimate': tax_estimate,
            'shipping_estimate': shipping_estimate,
            },status=status.HTTP_200_OK)


class AddItemView(StandardAPIView):
    permission_classes = (permissions.AllowAny,)
    def post(self, request, format=None):
        payload = validate_token(request)
        user_id = payload['user_id']
        data = request.data

        item_id = data['itemID']
        item_type = data['type']
        coupon_id = data.get('coupon', {}).get('id') if data.get('coupon') else None

        cart, created = Cart.objects.get_or_create(user=user_id)
        total_items = cart.total_items

        if item_type == 'Course':
            # Check if item already in cart
            if CartItem.objects.filter(cart=cart, course=item_id).exists():
                return self.send_error(
                    'Item is already in cart',
                    status=status.HTTP_409_CONFLICT)
        
            cart_item_object = CartItem.objects.create(course=item_id, cart=cart)

            if data.get('coupon') is not None:
                cart_item_object.coupon = coupon_id
                cart_item_object.save()

            # Check for referrer and save it if present
            if 'referrer' in data:
                referrer = data['referrer']
                cart_item_object.referrer = referrer
                cart_item_object.save()
            
            if CartItem.objects.filter(cart=cart, course=item_id).exists():
                # Update the total number of items in the cart
                total_items = int(cart.total_items) + 1
                Cart.objects.filter(user=user_id).update(
                    total_items=total_items
                )

        if item_type == 'Product':
            # Check if item already in cart
            if CartItem.objects.filter(cart=cart, product=item_id).exists():
                return self.send_error(
                    'Item is already in cart',
                    status=status.HTTP_409_CONFLICT)
            
            cart_item_object = CartItem.objects.create(product=item_id, cart=cart)
            
            if data.get('coupon'):
                coupon = data.get('coupon')
                coupon_id = coupon.get('id')
                if coupon_id:
                    cart_item_object.coupon = coupon_id
                    
            if data.get('shipping'):
                shipping_id = data.get('shipping').get('id')
                cart_item_object.shipping = shipping_id
                
            if data.get('color'):
                color_id = data.get('color').get('id')
                cart_item_object.color = color_id
                
            if data.get('size'):
                size_id = data.get('size').get('id')
                cart_item_object.size = size_id
                
            if data.get('weight'):
                weight_id = data.get('weight').get('id')
                cart_item_object.weight = weight_id
                
            if data.get('material'):
                material_id = data.get('material').get('id')
                cart_item_object.material = material_id
                
            cart_item_object.count = data.get('count')
            cart_item_object.save()
            
            # Update the total number of items in the cart
            total_items = int(cart.total_items) + 1
            Cart.objects.filter(user=user_id).update(
                total_items=total_items
            )
        

        cart_items = CartItem.objects.filter(cart=cart)
        items = []
        if CartItem.objects.filter(cart=cart).exists():
            for cart_item in cart_items:
                item = {}
                item['id'] = cart_item.id
                item['count'] = cart_item.count
                item['product'] = cart_item.product
                item['course'] = cart_item.course
                item['size'] = cart_item.size
                item['weight'] = cart_item.weight
                item['material'] = cart_item.material 
                item['color'] = cart_item.color
                item['shipping'] = cart_item.shipping
                item['coupon'] = cart_item.coupon
                items.append(item)
        return self.send_response({
            'cart':items,
            'total_items':total_items
            },status=status.HTTP_200_OK)


class RemoveItemView(StandardAPIView):
    permission_classes = (permissions.AllowAny,)
    def put(self, request, format=None):
        payload = validate_token(request)
        user_id = payload['user_id']
        cart, created = Cart.objects.get_or_create(user=user_id)
        total_items = cart.total_items
        data = request.data
        item_id = data['itemID']
        item_type = data['type']
        if item_type == 'Course':
            # Check if item Not already in cart
            if not CartItem.objects.filter(cart=cart, course=item_id).exists():
                return self.send_error(
                    'Item not in cart',
                    status=status.HTTP_409_CONFLICT)
            CartItem.objects.filter(cart=cart, course=uuid.UUID(item_id)).delete()
            if(cart.total_items > 0):
                total_items = int(cart.total_items) - 1
                cart.total_items=total_items
                cart.save()
        if item_type == 'Product':
            # Check if item Not already in cart
            if not CartItem.objects.filter(cart=cart, product=item_id).exists():
                return self.send_error(
                    'Item not in cart',
                    status=status.HTTP_409_CONFLICT)
            CartItem.objects.filter(cart=cart, product=uuid.UUID(item_id)).delete()

            if(cart.total_items > 0):
                total_items = int(cart.total_items) - 1
                cart.total_items=total_items
                cart.save()
        
        cart_items = CartItem.objects.filter(cart=cart)
        items = []
        if CartItem.objects.filter(cart=cart).exists():
            for cart_item in cart_items:
                item = {}
                item['id'] = cart_item.id
                item['count'] = cart_item.count
                item['product'] = cart_item.product
                item['course'] = cart_item.course
                item['size'] = cart_item.size
                item['weight'] = cart_item.weight
                item['material'] = cart_item.material
                item['color'] = cart_item.color
                item['shipping'] = cart_item.shipping
                item['coupon'] = cart_item.coupon
                items.append(item)

        return self.send_response({'cart':items,
            'total_items':total_items },status=status.HTTP_200_OK)


class ClearCartView(StandardAPIView):
    permission_classes = (permissions.AllowAny,)
    def get(self, request, format=None):
        payload = validate_token(request)
        user_id = payload['user_id']
        cart = get_object_or_404(Cart, user=user_id)
        cart_items = CartItem.objects.filter(cart=cart)
        cart_items.delete()
        serializer = CartSerializer(cart)
        return self.send_response(serializer.data,status=status.HTTP_200_OK)


class UpdateItemView(StandardAPIView):
    permission_classes = (permissions.AllowAny,)
    def put(self, request, format=None):
        payload = validate_token(request)
        user_id = payload['user_id']
        cart, created = Cart.objects.get_or_create(user=user_id)
        total_items = cart.total_items
        data = request.data
        item_id = data['itemID']
        count = data['value']

        # UPDATE CART LOGIC
        if not CartItem.objects.filter(cart=cart, product=item_id).exists():
            return Response(
                {'error': 'This product is not in your cart'},
                status=status.HTTP_404_NOT_FOUND)
        
        product_response = requests.get(f'{products_ms_url}/api/products/get/' + item_id+'/').json()['results']
        quantity = product_response.get('details').get('quantity')

        count = int(count)
        if count <= quantity:
            CartItem.objects.filter(
                product=item_id, cart=cart
            ).update(count=count)

            cart_items = CartItem.objects.filter(cart=cart)
            items = []
            if CartItem.objects.filter(cart=cart).exists():
                for cart_item in cart_items:
                    item = {}
                    item['id'] = cart_item.id
                    item['count'] = cart_item.count
                    item['product'] = cart_item.product
                    item['course'] = cart_item.course
                    item['size'] = cart_item.size
                    item['weight'] = cart_item.weight
                    item['material'] = cart_item.material
                    item['color'] = cart_item.color
                    item['shipping'] = cart_item.shipping
                    item['coupon'] = cart_item.coupon
                    items.append(item)
            return self.send_response({
                'cart':items,
                'total_items':total_items 
            },status=status.HTTP_200_OK)
        else:
            return self.send_error('Product does not have enough stock.',status=status.HTTP_409_CONFLICT)


class SynchCartItemsView(StandardAPIView):
    permission_classes = (permissions.AllowAny,)

    def put(self, request, format=None):
        payload = validate_token(request)
        user_id = payload['user_id']
        data = request.data

        cart, created = Cart.objects.get_or_create(user=user_id)
        cart_items = data['cart_items']

        items = []
        courses = []
        products = []

        for item in cart_items:
            if item['type'] == 'Course':
                courses.append(item)
            elif item['type'] == 'Product':
                products.append(item)

        # Add courses to the cart
        for course in courses:
            course_id = course['course_id']
            coupon = course['coupon'] if course['coupon'] else None
            referrer = course['referrer'] if course['referrer'] else None

            # Update or create the CartItem for the course
            cart_item, _ = CartItem.objects.update_or_create(
                cart=cart, course=course_id,
                defaults={'coupon': coupon, 'referrer': referrer}
            )
            items.append(cart_item)

        # Add products to the cart
        for product in products:
            product_id = product['product_id']
            count = product['count']
            size = product['size'] if product['size'] else None
            weight = product['weight'] if product['weight'] else None
            material = product['material'] if product['material'] else None
            color = product['color'] if product['color'] else None
            shipping = product['shipping'] if product['shipping'] else None
            coupon = product['coupon'] if product['coupon'] else None
            referrer = product['referrer'] if product['referrer'] else None

            # Update or create the CartItem for the product
            cart_item, _ = CartItem.objects.update_or_create(
                cart=cart, product=product_id,
                defaults={
                    'count': count, 'size': size, 'weight': weight,
                    'material': material, 'color': color, 'shipping': shipping,
                    'coupon': coupon, 'referrer': referrer
                }
            )
            items.append(cart_item)

        total_items = cart.total_items
        return self.send_response({'cart': items, 'total_items': total_items}, status=status.HTTP_200_OK)
