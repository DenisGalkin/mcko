// 2025-03-18 - исправлена ошибка с восстановлением значений value, содержащих пробелы
// 2024-08-29 - для вкладок добавлен класс default, чтобы задать активную по умолчанию вкладку
// 2024-08-22 - добавлен функционал Вкладки 2.0
// 2023-04-13 - double SaveButton fix
// 2022-01-15 - multidroppable + h
// 2021-03-26 - added $().select2 support

// InProcess = 0;
var InProcess;
var SliderPosition = 1;
var SliderPrevBottom;

var GlobalSelectActive=0;
var SelActive = 0;
var SelMode = 0;
var MinAnswerHeight = 200;
var MaxAnswerHeight = 500;
var StaticMode = 0; // 0 - можно сворачивать задания;

// multidroppable-переменные:
var md_ans = []; // массив с ответами, аналог bvalue
var md_sep = ''; // разделитель - или пустая строка, или запятая
var md_MaxZ = 1; // текущий максимальный z-index
var sourceID, destinationID;

// multidroppable - выстраивает перетащенные элементы друг за другом
function ReorderDroppable(destinationID) {
	CurAnswer = md_ans[destinationID].split(md_sep);
	$('#bvalue'+destinationID).val( md_ans[destinationID] );
	n=0;
	CurAnswer.forEach(function(element) {
		if ($('#droppable'+destinationID).hasClass('h')) {
			// горизонтальное выстраивание элементов:
			if (n==0) $('#draggable'+element).position({my: "left center",at: "left+3 center",of: "#droppable"+destinationID,collision:"none"});
			else $('#draggable'+element).position({my: "left center",at: "right+3 center",of: "#draggable"+prev,collision:"none"});
		} else {
			// вертикальное выстраивание (по умолчанию, если у multidroppable-элемента не задан дополнительный класс h)
			if (n==0) $('#draggable'+element).position({my: "center top",at: "center top+3",of: "#droppable"+destinationID,collision:"none"});
			else $('#draggable'+element).position({my: "center top",at: "center bottom+3",of: "#draggable"+prev,collision:"none"});
		}
	  prev = element;
	  n++;
	});
}

// Отображаем время проигывания
function UpdateAudioTimer(t) {
console.log(t.duration);
	dur = Math.floor(t.duration);
	dur_mm = div(dur, 60);
	dur_ss = dur % 60;
	if (dur_ss<10) dur_ss = '0'+dur_ss;

	cur = Math.floor(t.currentTime);
	cur_mm = div(cur, 60);
	cur_ss = cur % 60;
	if (cur_ss<10) cur_ss = '0'+cur_ss;

	$("#PlayerTimer").html(cur_mm+':'+cur_ss+' / '+dur_mm+':'+dur_ss);
};

function MakeSelectable(what) {
	var arr;
	var out='';
	arr = $(what).html().split(" ");

	// Каждое слово оборачиваем в SPAN с классом ss
	arr.forEach(function(item, index, array) {
		out = out + '<span class="ss"> '+item+'</span>';
	});

	$(what).html(out);

	// Далее навешиваем события
	$('*').on("mousedown", function() { SelActive = 1; });

	$('.ss').on("mousemove", function() {
		if (GlobalSelectActive==0) return;
		if (SelActive==0) return;
		// console.log('SEL-2: ' + $(this).html());
		if (SelMode==0) {
			if ($(this).hasClass('selected')) SelMode = -1; else SelMode = 1;
		}
		if (SelMode==1) $(this).addClass('selected'); else $(this).removeClass('selected');
	  });
	
	$('*').on("mouseup", function() { SelActive = 0; SelMode = 0; });
}

function UpdateAnswerHeight() {
	NeedHeight = $("#AnswerSlider").prop("scrollHeight");
	if (NeedHeight<MinAnswerHeight) NeedHeight = MinAnswerHeight;
	if (NeedHeight>MaxAnswerHeight) NeedHeight = MaxAnswerHeight;
	$("#AnswerSlider").css('height', NeedHeight + 'px');
	ButtonNewBottom = NeedHeight+70;
	$("#ToggleButton").css('bottom',ButtonNewBottom+'px');
}

// Assign save function when document is fully loaded and ready
// $(function() {
$( window ).on( "load", function() {
	AlreadyLoaded = 1;

// Для проигрывателя mp3 - регулировка громкости
$( "#slider" ).slider({value: 100,
	slide: function( event, ui ) {
			console.log( ui.value );
			document.getElementById("player").volume = ui.value/100;
		}
});

function SetAnswerB() {
	// window.onbeforeunload = null;
	$(window).off('beforeunload');
	document.forms["AnswerForm"].submit();
}

function FormAnswer(n) {
//	document.getElementById("qanswer"+n).checked = ! document.getElementById("qanswer"+n).checked;
	r = '';
	if ($('#qanswer1:checked').length) r=r+'1';
	if ($('#qanswer2:checked').length) r=r+'2';
	if ($('#qanswer3:checked').length) r=r+'3';
	if ($('#qanswer4:checked').length) r=r+'4';
	if ($('#qanswer5:checked').length) r=r+'5';
	if ($('#qanswer6:checked').length) r=r+'6';
	if ($('#qanswer7:checked').length) r=r+'7';
	if ($('#qanswer8:checked').length) r=r+'8';
	if ($('#qanswer9:checked').length) r=r+'9';
	if ($('#qanswer10:checked').length) r=r+'10';
	if ($('#qanswer11:checked').length) r=r+'11';
	if ($('#qanswer12:checked').length) r=r+'12';
	if ($('#qanswer13:checked').length) r=r+'13';
	if ($('#qanswer14:checked').length) r=r+'14';
	if ($('#qanswer15:checked').length) r=r+'15';
	document.getElementById("bvalue0").value = r;
}

if (InProcess) {
	var TIME_LEFT, mm, ss, TimeFont;
	var TimeFix = RightNow - Math.round(new Date().getTime() / 1000);
	
	var b1 = document.getElementById("AnswerHere");//блок перед которым ставим
	var b2 = document.getElementById("b");//блок который передвигаем
	b1.parentNode.insertBefore(b2, b1);
	b2.style.display = ShowBAnswer;

	var timer = window.setInterval( UpdateTimer, 1000);
	UpdateTimer();
} // END: InProcess

function div(val, by){ return (val - val % by) / by; }

function UpdateTimer() {
	if (InProcess) {
		TIME_LEFT = xFINISH - Math.round(new Date().getTime() / 1000) - TimeFix;
		mm = div(TIME_LEFT, 60);
		ss = TIME_LEFT % 60;
		if (ss<10) ss = '0'+ss;
		if (mm<5) TimeFont = '<font color=red>'; else TimeFont = '<font>';
		/* $("#topline").html( TimeFont+'Оставшееся время - '+ mm+':'+ss+'</font>' ); */
		$("#topline").html( mm+':'+ss );
		if (TIME_LEFT<0) document.location="?n=998";
	}
}

function UpdateEvents() {
  	$(".save:not(.DoneAlready)").on( "click", function() {
	  // Если текущий элемент содержит номер следующего вопроса "n", то его следует учесть:
	  if ($(this).attr('name')=='n' && $(this).attr('value').length) $('#GoNext').val( $(this).attr('value') );
	  // Необходимо для сохранения значения "по умолчанию", если не было onchange:
	  $("textarea.ans").trigger('change');
	  //$("#AnswerForm").submit();
/*-----------------*/
//$("#AnswerSlider").html('loading...');
$.ajax({
	  url: "?ajax=1",
	  method: "POST",
	  dataType: 'json',
	  data: $('#AnswerForm').serialize()
	}).done(function(result) {
		if (result.state=='OK') {
			//alert(result.message);
			if (StaticMode) result.content = result.content + '<br><br><br><br>';
			$("#AnswerSlider").html(result.content);

			$("#qline").html(result.qline);
			if (StaticMode) {
				$("#BottomButtons").addClass('BottomButtonsStatic');
				$("#AnswerSlider").css('height', 'auto');
			} else {
				$("#AnswerSlider").css('height', MinAnswerHeight+'px');
				if (SliderPosition==0) $("#ToggleButton").trigger('click');
				UpdateAnswerHeight();
			}
/*
			NeedHeight = $("#AnswerSlider").prop("scrollHeight");
			if (NeedHeight<MinAnswerHeight) NeedHeight = MinAnswerHeight;
			if (NeedHeight>MaxAnswerHeight) NeedHeight = MaxAnswerHeight;
			$("#AnswerSlider").css('height', NeedHeight + 'px');
			ButtonNewBottom = NeedHeight+70;
			$("#ToggleButton").css('bottom',ButtonNewBottom+'px');
*/
			UpdateEvents();
		}
		else alert(result.message);		
	});
	} );
// on save

$(".save:not(.DoneAlready)").addClass('DoneAlready');

/*
// Для выпадающих SELECT-списков автоматически сохраняем значение в bvalueX
$( "select.ans" ).on( "change", function(event) {
	// console.log('select changed ' + $(this).attr('name') + ' = ' + $(this).val() );
	if ( $(this).attr('name').substr(0,1)=='a' ) $('#bvalue'+$(this).attr('name').substr(1)).val( $(this).val() );
});
*/
// Для выпадающих SELECT-списков автоматически сохраняем значение в bvalueX
$( "select" ).on( "change", function(event) {
	// console.log('select changed ' + $(this).attr('name') + ' = ' + $(this).val() );
	if (!$(this).attr('id')) return;
	if ( $(this).attr('id').substr(0,1)=='a' ) $('#bvalue'+$(this).attr('id').substr(1)).val( $(this).val() );
});

/*
$( "input.ans,textarea.ans" ).on( "change", function(event) {
	// console.log('input changed');
	if ( $(this).attr('name').substr(0,1)=='a' ) {
		$('#bvalue'+$(this).attr('name').substr(1)).val( $(this).val() );

		// checkbox типа a0 - исключение, если не стоит галка, то сохраняем пустую строку
		if ( $(this).attr('type')=='checkbox')
			if (!$(this).prop('checked')) $('#bvalue'+$(this).attr('name').substr(1)).val("");
	}
});
*/

$("input").attr("autocomplete", "off");
$("input,textarea").attr("spellcheck", "false");

$("input,textarea").on( "change", function(event) {
	// console.log('input changed');
	if (!$(this).attr('id')) return;
	if ( $(this).attr('id').substr(0,1)=='a' ) {
		$('#bvalue'+$(this).attr('id').substr(1)).val( $(this).val() );

		// checkbox типа a0 - исключение, если не стоит галка, то сохраняем пустую строку
		if ( $(this).attr('type')=='checkbox')
			if (!$(this).prop('checked')) $('#bvalue'+$(this).attr('id').substr(1)).val("");
	}
});

// Обработчик нажатия на активные ans-элементы - варианты ответов, дистракторы и т.д.
$( "input.ans[type=checkbox],input.ans[type=radio],span.ans[name],div.ans[name]" ).on( "click", function(event) {
  // Задания типа "a" - одиночный выбор значения
  if ( $(this).attr('name').substr(0,1)=='a' ) {
	$('[name="'+$(this).attr('name')+'"]').removeClass('marked');
	$(this).addClass('marked');
	$('#bvalue'+$(this).attr('name').substr(1)).val( $(this).attr('value') );
	if ( $(this).attr('type')=='checkbox') {
		CurState = $(this).prop('checked');
		$('[name="'+$(this).attr('name')+'"]').prop('checked', false);
		$(this).prop('checked', CurState);
		if (CurState==true) $('#bvalue'+$(this).attr('name').substr(1)).val( $(this).attr('value') );
		else $('#bvalue'+$(this).attr('name').substr(1)).val("");
	}
  }

  // Задания типа "m" - множественный выбор
  var answer1 = ''; // множ. ответ без разделителей
  var answer2 = ''; // множ. ответ с разделителем "запятая"
  var UseSeparator = 0;
  if ( $(this).attr('name').substr(0,1)=='m' ) {
	$(this).toggleClass('marked');
	$('[name='+$(this).attr('name')+']').each(function() {
	  if ($(this).attr('value').length>1) UseSeparator = 1;
	  if ($(this).hasClass('marked')) {
			answer1 = answer1 + $(this).attr('value');
			answer2 = answer2 + ',' + $(this).attr('value');
			// console.log( $(this).attr('value') );
		}
	});

	if (UseSeparator) $('#bvalue'+$(this).attr('name').substr(1)).val( answer2.substr(1) );
				 else $('#bvalue'+$(this).attr('name').substr(1)).val( answer1 );

  } // !m

}); // END: $( "span.ans,div.ans" ).on( "click"...


// Восстанавливаем сохраненные в bvalue0+ значения в "визуальные" клиентские элементы
// a0+ и m0+, чтобы сохраненные значения "подсвечивались" визуально через класс marked
var i=0;
while ($('#bvalue'+i).length) {
	var TempValues;

  	// Восстанавливаем одиночный выбор для SPAN
	if ($('span.ans[name="a'+i+'"]').length && $('#bvalue'+i).val().length )
		$('[name="a'+i+'"][value="'+$('#bvalue'+i).val()+'"]').addClass('marked');

  	// Восстанавливаем одиночный выбор для DIV
	if ($('div.ans[name="a'+i+'"]').length && $('#bvalue'+i).val().length )
		$('[name="a'+i+'"][value="'+$('#bvalue'+i).val()+'"]').addClass('marked');

  	// Восстанавливаем одиночный выбор для INPUT TYPE="CHECKBOX"
	if ($('input.ans[name="a'+i+'"][type=checkbox]').length && $('#bvalue'+i).val().length ) {
		$('[name="a'+i+'"][value="'+$('#bvalue'+i).val()+'"]').prop('checked', true);
		$('[name="a'+i+'"][value="'+$('#bvalue'+i).val()+'"]').addClass('marked'); // для порядка
	}

  	// Восстанавливаем одиночный выбор для INPUT TYPE="RADIO"
	if ($('input.ans[name="a'+i+'"][type=radio]').length && $('#bvalue'+i).val().length ) {
		$('[name="a'+i+'"][value="'+$('#bvalue'+i).val()+'"]').prop('checked', true);
		$('[name="a'+i+'"][value="'+$('#bvalue'+i).val()+'"]').addClass('marked'); // для порядка
	}

	$('select#a'+i).val( $('#bvalue'+i).val() );
	$('input#a'+i).val( $('#bvalue'+i).val() );
	if ($('#bvalue'+i).val()!='') $('textarea#a'+i).val( $('#bvalue'+i).val() );

	// Восстанавливаем множественный выбор
	if ($('.ans[name="m'+i+'"]').length) {
		UseSeparator = '';
		$('.ans[name="m'+i+'"]').each(function() { if ($(this).attr('value').length>1) UseSeparator = ','; });
		TempValues = $('#bvalue'+i).val().split( UseSeparator );

		TempValues.forEach(function(element) {
			$('[name="m'+i+'"][value="'+element+'"]').addClass('marked');
			$('[name="m'+i+'"][value="'+element+'"][type=checkbox]').prop('checked', true);
		});

		if ($('#bvalue'+i).val()=='') $('#bvalue'+i).val('-');

	}
  i++;
}


// Перемещаемые мышкой блоки, для которых есть принимающие блоки
/*
droppable - принимающее поле
draggable - переносимое мышкой поле
droppableX == X - номер подответа, куда автоматом сохранять значение bvalueX
draggableY == Y - сохраняемое число-ответ, обычно номер перемещаемого блока

<div class="droppable" id="droppable0">поле bvalue0</div>
<div class="droppable" id="droppable1">поле bvalue1</div>
<div class="droppable" id="droppable2">поле bvalue2</div>

<div style="clear:both"></div> <!-- ############## -->

<div class="draggable" id="draggable1">Ответ 1</div>
<div class="draggable" id="draggable2">Ответ 2</div>
<div class="draggable" id="draggable3">Ответ 3</div>

<div style="clear:both"></div> <!-- ############## -->
*/


$('.draggable').draggable({
	zIndex: 100,
	start: function( event, ui ) { ui.helper.css('z-index', window.md_MaxZ++); /* console.log(window.md_MaxZ);*/ }
});

$('.droppable').droppable({
	out: function(event, ui) {
	  sourceID = ui.draggable[0].id.replace('draggable','');
	  destrinationID = this.id.replace('droppable','');
	  if ($('#bvalue'+destrinationID).val()==sourceID) $('#bvalue'+destrinationID).val('').change();
	},
	drop: function(event, ui) {
	  sourceID = ui.draggable[0].id.replace('draggable','');
	  destrinationID = this.id.replace('droppable','');
	  // $(ui.draggable[0]).position({my: "center",at: "center",of: "#droppable"+destrinationID});
	  $('#draggable'+sourceID).position({my: "center",at: "center",of: "#droppable"+destrinationID});
	  $('#bvalue'+destrinationID).val( sourceID ).change();
	  
	  // alert('Sorce='+sourceID+'   Destination='+destrinationID);
	}
});

// Восстанавливаем позиции ранее сохраненных переносимых блоков
$(".droppable").each(function( x ) {
	temp_nn = this.id.replace('droppable','');
	// temp_nn = this.id.slice(9);
	if ($('#bvalue' + temp_nn).val()!='') $('#draggable'+$('#bvalue' + temp_nn).val()).position({my: "center",at: "center",of: "#droppable"+temp_nn});
});

// Проверяем, есть ли двухсимвольные перетаскиваемые элементы, чтобы использовать запятую как разделитель для multidroppable
$('.draggable').each(function( index ) {
	if ($( this )[0].id.replace('draggable','')>=10) md_sep = ',';
});

// Восстанавливаем сохранённые значения
$('.multidroppable').each(function( index ) {
	ThisID = ($( this )[0].id.replace('droppable',''));
	md_ans[ThisID]  = $('#bvalue'+ThisID).val();
	if (md_ans[ThisID]===undefined) md_ans[ThisID] = '';
	ReorderDroppable(ThisID);
	// console.log(md_ans[ThisID]);
});

$('.multidroppable').droppable({
	out: function(event, ui) {
		sourceID = ui.draggable[0].id.replace('draggable','');
		destinationID = this.id.replace('droppable','');
		md_ans[destinationID] = (md_sep + md_ans[destinationID] + md_sep).replace(md_sep + sourceID + md_sep, md_sep);
		md_ans[destinationID] = md_ans[destinationID].replace(/,,/g,',');
		md_ans[destinationID] = md_ans[destinationID].replace(/^,/g,'');
		md_ans[destinationID] = md_ans[destinationID].replace(/,$/g,'');
		ReorderDroppable(destinationID);
	}, // !out

	drop: function(event, ui) {
		sourceID = ui.draggable[0].id.replace('draggable','');
		destinationID = this.id.replace('droppable','');
		if ((md_sep + md_ans[destinationID] + md_sep).search(md_sep + sourceID + md_sep)==-1) {
			CurAnswer = md_ans[destinationID].split(md_sep);
			CurAnswer.push(sourceID);
			CurAnswer.sort(function(a, b){return a-b});
			md_ans[destinationID] = '';
			CurAnswer.forEach(function(element) {
				md_ans[destinationID] = md_ans[destinationID] + md_sep + element;
			});
			md_ans[destinationID] = md_ans[destinationID].replace(/^,*/g,'');
			ReorderDroppable(destinationID);
		} // if cur answer was not added yet
	} // !drop
});

} // END: function UpdateEvents()
// ########################
UpdateEvents();

/*
function XResized() {
	$('#qline').height( $('.leftmenu').height() - $('#topline:visible').height());
	if ($('.qramka').length > 0) {
		ScrollPos = $('.qramka').get(0).offsetTop - $('#qline').height() / 2;
		if (ScrollPos>0) $('#qline').mCustomScrollbar("scrollTo", ScrollPos );
	}
	BottomScrollArrow();
}
*/

function BottomScrollArrow() {
	if ($('.rightcontent2').length > 0 && $('#down_arrow').length > 0)
		if ($('.rightcontent2').get(0).scrollHeight>$('.rightcontent2').get(0).offsetHeight+$('.rightcontent2').get(0).scrollTop) $('#down_arrow').show(); else $('#down_arrow').hide();
}

$("#ToggleButton").on( "click", function() {
	if (SliderPosition==1) {
		console.log('Minimizing!!!');
		SliderPrevBottom = $("#ToggleButton").css('bottom');
		$("#AnswerSlider").hide( "drop", { direction: "down" });
		$("#ToggleButton").css('bottom','0px');
		$("#vCaption").html('^');
		SliderPosition = 0;
	} else {
		console.log('Maximazimg!!!');
		$("#AnswerSlider").show();
		$("#ToggleButton").css('bottom',SliderPrevBottom);
		$("#vCaption").html('V');
		SliderPosition = 1;
	}
});

/*
$(window).resize( XResized );
$('.rightcontent2').scroll( BottomScrollArrow );
$('#qline').mCustomScrollbar({  theme:"minimal", axis:"y", scrollInertia:0  });
BottomScrollArrow();
XResized();
*/

$('#SelectButton').on("mousedown", function() {
	if (GlobalSelectActive==0) {
		GlobalSelectActive=1;
		$(this).addClass('activated');
		$('.ss').addClass('noselect');
	} else {
		GlobalSelectActive=0;
		$(this).removeClass('activated');
		$('.ss').removeClass('noselect');
	}
});

// == Вкладки 2.0 ========

if ($('#xmenu').length) {
	let temp='', CurID, i=0, DefaultTabID;
	$('.xtab').each(function() {
		i++;
		CurID = 'AutoTabID' + i;
		$(this).attr("id", CurID);
		$(this).detach().appendTo('#xcontent');
		temp = temp +	'<a href="#" class="tab_link" id="TabLink'+i+'" onclick="$(\'.xtab\').hide(); $(\'#'+CurID+'\').show(); $(\'.tab_link\').removeClass(\'act\'); $(this).addClass(\'act\'); return false;">' + $(this).attr('xtitle') + '</a>';
		if (i==1 || $(this).hasClass('default')) DefaultTab = i;
	});

	$('#xmenu').html(temp);

	$('#AutoTabID'+DefaultTab).show();
	$('#TabLink'+DefaultTab).addClass('act');
} // ! #xmenu

// Устанавливаем высоту для блока, в котором отображается содержимое вкладок
if ($('#xcontent').length) $('#xcontent').height( 0.6 * ($(window).height() - $('#xcontent').offset().top) );

// END: Вкладки 2.0 =======


UpdateAnswerHeight();

// Если подключено дополнение для красивых и удобных выпадающих списков select2, то используем его
if (typeof $().select2=='function') $('select').select2();

// Добавляем кнопку "сохранить ответ", если её нет на странице (зависит от типа задания)
if (!$('#SaveButton').length) $("#AnswerHere").html('<button onclick="SetAnswerB()" style="margin-top:15px">Сохранить ответ</button>');

/*
		console.log('Minimizing!!!');
		SliderPrevBottom = $("#ToggleButton").css('bottom');
		$("#AnswerSlider").hide();
		$("#ToggleButton").css('bottom','0px');
		$("#vCaption").html('^');
		SliderPosition = 0;
*/
});
// END: $(function().. when document is fully loaded and ready
