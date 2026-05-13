/*
Virtual keyboard plugin by Oleg [MCKO] 2021-12-12
<input type="text" keys="m;c;ko">
*/

var CurInput;
var PreKeys = new Map();

// Preload virt.keyboard layouts:
PreKeys.set('NEM','ÄäÜüÖöß'); /* немецкий язык */
PreKeys.set('ISP','ÑñÁáÉéÍíóÓÚú'); /* испанский язык */
PreKeys.set('FRA','ÀàÂâÇçÉéÊêÈèËëÎîÏïÔôÙùÛû'); /* французский язык */
PreKeys.set('ENG','abcdefghijklmnopqrstuvwxyz');
PreKeys.set('RUS','абвгдеёжзийклмнопрстуфхцчшщъыьэюя');

$(function() {

	$('body').append('<div id="kb" class="kb"></div>');
	$('div#kb').click(function(){ $(CurInput).focus(); });

	$("input,textarea").focus(function() {
		if ($(this).attr('keys')===undefined) return;
		CurInput = $(this);
		keys = $(this).attr('keys');
		if (PreKeys.get(keys)!==undefined) keys = PreKeys.get(keys);
		UseSeparator = ''; if (keys.indexOf(';')>=0) UseSeparator = ';';
		buf = '';
		keys.split(UseSeparator).forEach(function(ch) { buf += '<button onclick="TypeChar(this)">'+ch+'</button>'; });
		$("#kb").html('<center><b>Фрагмент виртуальной клавиатуры:</b><br> ' + buf + '</center>');
		$("#kb").fadeIn();
	});

	$('*').click(function(x) { HideKeyboard(); });
});

function TypeChar(t) {
	p = $(CurInput)[0].selectionStart;
	s = $(CurInput).val();
	c = $(t).html();
	$(CurInput).val(s.substr(0,p) + c + s.substr(p,99999));
	$(CurInput).focus().change()[0].setSelectionRange(p+c.length, p+c.length);
}

function HideKeyboard() {
	if (!$(CurInput).is(":focus")) $("#kb").fadeOut();
}
